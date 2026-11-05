import core
import asyncio
import copy
import time

class Subagents(core.module.Module):
    """Lets your AI spin up subagents (chat sessions with a seperate context) to perform a request"""

    category = "core"

    settings = {
        "allow_running_in_background": {
            "description": "Allow running subagents in the background, instead of having the main session wait for the subagent to finish. Only works well if you have support for concurrent requests configured in your chosen AI inference server. AI can still choose to run a subagent in the foreground.",
            "default": False
        },
        "max_background_subagents": {
            "type": "number",
            "description": "Maximum amount of subagents that should be allowed to run at once",
            "default": 2,
            "depends": "allow_running_in_background"
        },
    }

    async def _process_substream(self, stream, ctx):
        final_content = []
        tool_calls_occurred = False
        async for token in stream:
            yield token

            token_type = token.get("type")
            if token_type == "content":
                final_content.append(token.get("content"))
            elif token_type == "tool_calls":
                tool_calls_occurred = True
                toolcall_request = await self.channel.tc_manager._build_recursive_request(token, [], [])
                async for sub_token in self.channel.tc_manager.process(toolcall_request, context=ctx):
                    sub_type = sub_token.get("type")

                    # collect the final response
                    if sub_type == "final":
                        ctx.append(sub_token.get("content"))

                    yield sub_token

        if final_content and not tool_calls_occurred:
            ctx.append({"role": "assistant", "content": "".join(final_content)})

    async def on_ready(self):
        self.subagent_jobs = {}

    async def _run_job(self, job_id, subagent_request):
        ctx = copy.deepcopy(subagent_request)
        job = self.subagent_jobs[job_id]
        job["ctx"] = ctx
        
        try:
            async for token in self._process_substream(
                self.manager.API.send_stream(subagent_request),
                ctx
            ):
                # only needs to accumulate into 'ctx', lol
                pass

            last_msg = (ctx[-1] if len(ctx) else {})
            job["result"] = last_msg.get("content") or ""
            job["done"] = True

            if job.get("result"):
                await self.channel.push({"role": "assistant", "content": job["result"] or f"Subagent {job_id} found no results!"})
        except Exception as e:
            job["done"] = True
            job["error"] = core.detail_error(e)

    @core.module.tool(bypass_timeout=True)
    async def spawn(self, prompt: str, run_in_background: bool = False):
        subagent_request = [
            {
                "role": "system",
                "content": await self.channel.context.chat.get_system_prompt()
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        if run_in_background and self.config.get("allow_running_in_background"):
            job_id = f"subagent-{int(time.time())}"
            job = { "task": None, "ctx": None, "done": False, "result": None, "error": None }
            self.subagent_jobs[job_id] = job
            job["task"] = asyncio.create_task(self._run_job(job_id, subagent_request))

            return self.result({
                "job_id": job_id,
                "status": "running",
                "note": "subagent running in background. will push its results into current channel when done. use check_subagent with this job_id to retrieve its results at any time."
            })
        else:
            # hold a temporary context for this call
            ctx = copy.deepcopy(subagent_request)

            try:
                await self.channel.on_stream(
                    self._process_substream(
                        self.manager.API.send_stream(subagent_request),
                        ctx
                    )
                )

                final_msg = ctx[-1] if ctx else {}
                results = final_msg.get("content") or ""
            except Exception as e:
                return self.result(core.detail_error(e), success=False)

            return self.result({"status": "done", "results": results})

    @core.module.tool
    async def check(self, job_id: str):
        """check the status or retrieve the results of a backgrounded subagent job"""
        job = self.subagent_jobs.get(job_id)
        if job is None:
            return self.result(f"no subagent job with id {job_id}", success=False)

        if not job["done"]:
            latest_message = {}
            ctx = job.get("ctx") or []
            if len(ctx) > 0:
                # find latest message with role assistant
                for index in range(len(ctx) - 1, -1, -1):
                    if ctx[index].get("role") == "assistant":
                        latest_message = ctx[index]
                        break

            return self.result({"status": "still running", "current_last_message": latest_message})

        if job["error"]:
            del self.subagent_jobs[job_id]
            return self.result(job["error"], success=False)

        # prune after reading so the dict doesn't grow forever
        del self.subagent_jobs[job_id]

        return self.result({"status": "done", "result": job["result"]})

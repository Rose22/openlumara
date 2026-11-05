import core
import asyncio
import copy
import time

class Subagents(core.module.Module):
    """Lets your AI spin up subagents (chat sessions with a seperate context) to perform a request"""

    category = "core"

    settings = {
        "run_in_background": {
            "description": "Run subagents in the background, instead of having the main session wait for the subagent to finish. Only works well if you have support for concurrent requests configured in your chosen AI inference server.",
            "default": False
        },
        "max_background_subagents": {
            "type": "number",
            "description": "Maximum amount of subagents that should be allowed to run at once",
            "default": 2,
            "depends": "run_in_background"
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

        if not self.config.get("run_in_background"):
            self.disabled_tools.append("check")

    async def _run_job(self, job_id, subagent_request):
        ctx = list(subagent_request)
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

            # don't push when the job's results have already been checked with subagents_check()
            if not self.channel._chain_idle.is_set():
                await self.channel._chain_idle.wait()

            claimed = self.subagent_jobs.pop(job_id, None)
            if claimed is not None:
                await self.channel.push(
                    {"role": "assistant", "content": job["result"] or f"Subagent {job_id} found no results!"},
                    defer=True
                )
        except Exception as e:
            job["done"] = True
            job["error"] = core.detail_error(e)

            # push the failure too so the main agent learns without polling
            if not self.channel._chain_idle.is_set():
                await self.channel._chain_idle.wait()

            claimed = self.subagent_jobs.pop(job_id, None)
            if claimed is not None:
                await self.channel.push(
                    {"role": "assistant", "content": f"Subagent {job_id} errored: {job['error']}"},
                    defer=True
                )

    @core.module.tool(bypass_timeout=True)
    async def spawn(self, title: str, prompt: str):
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

        if self.config.get("run_in_background"):
            job_id = f"subagent-{int(time.time())}"
            job = { "task": None, "title": title, "ctx": None, "done": False, "result": None, "error": None }
            self.subagent_jobs[job_id] = job
            job["task"] = asyncio.create_task(self._run_job(job_id, subagent_request))

            return self.result({
                "job_id": job_id,
                "status": "running",
                "note": "subagent running in background. will push its results into current channel when done. use check_subagent with this job_id to retrieve its results at any time."
            })
        else:
            # hold a temporary context for this call
            ctx = list(subagent_request)

            try:
                await self.channel.on_stream(
                    self._process_substream(
                        self.manager.API.send_stream(subagent_request),
                        ctx
                    )
                )

                if len(ctx) <= 1:
                    return self.result(f"subagent for task '{title}' returned a blank response", success=False)

                last_msg = (ctx[-1] if len(ctx) else {})
                results = last_msg.get("content") or ""

                return self.result({"status": "done", "results": results})
            except Exception as e:
                return self.result(core.detail_error(e), success=False)

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

            return self.result({"title": job["title"], "status": "still running", "current_last_message": latest_message})

        if job["error"]:
            del self.subagent_jobs[job_id]
            return self.result(job["error"], success=False)

        # prune after reading so the dict doesn't grow forever
        del self.subagent_jobs[job_id]

        return self.result({"title": job["title"], "status": "done", "result": job["result"]})

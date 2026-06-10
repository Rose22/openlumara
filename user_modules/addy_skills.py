import core
import os

class AddySkills(core.module.Module):
    """
    Integrates Addy Osmani's Agent-Skills by injecting markdown skill files into the system prompt.
    """

    settings = {
        "enabled_skills": {"type": "array", "default": []}
    }

    def _get_skills_dir(self):
        # We put the downloaded skills in data/skills/
        skills_dir = os.path.join(core.get_data_path(), "skills")
        if not os.path.exists(skills_dir):
            os.makedirs(skills_dir, exist_ok=True)
        return skills_dir

    async def on_ready(self):
        # ensure directory exists on boot
        self._get_skills_dir()

        # We can also search in user_modules/data/skills/ if they were copied there
        # but let's copy them to core.get_data_path()/skills if they are in user_modules/data/skills
        # and delete user_modules/data/skills to keep it clean.

        src_dir = os.path.join(core.get_path("user_modules"), "data", "skills")
        dst_dir = self._get_skills_dir()

        if os.path.exists(src_dir):
            for file in os.listdir(src_dir):
                if file.endswith(".md"):
                    src_file = os.path.join(src_dir, file)
                    dst_file = os.path.join(dst_dir, file)
                    with open(src_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    with open(dst_file, "w", encoding="utf-8") as f:
                        f.write(content)

            # we don't strictly need to delete src_dir, but we've successfully copied them to the right place.

        core.log("addy_skills", "Addy-Skills Module loaded.")

    @core.module.command("skill list", help="List all available and enabled Addy Agent Skills.")
    async def list_skills(self):
        skills_dir = self._get_skills_dir()
        available_skills = [f.replace(".md", "") for f in os.listdir(skills_dir) if f.endswith(".md")]
        enabled_skills = self.config.get("enabled_skills") or []

        if not available_skills:
            msg = "No skills found in data/skills/."
        else:
            msg = "Available Skills:\n"
            for skill in available_skills:
                status = "[ENABLED]" if skill in enabled_skills else "[DISABLED]"
                msg += f"- {skill} {status}\n"

        if self.channel:
            self.channel.announce(msg)

    @core.module.command("skill enable", help="Enable a specific Addy Agent Skill.")
    async def enable_skill(self, skill_name: str):
        skills_dir = self._get_skills_dir()
        available_skills = [f.replace(".md", "") for f in os.listdir(skills_dir) if f.endswith(".md")]

        if skill_name not in available_skills:
            msg = f"Skill '{skill_name}' not found. Use '/skill list' to see available skills."
            if self.channel:
                self.channel.announce(msg)
            return

        enabled_skills = self.config.get("enabled_skills") or []
        if skill_name not in enabled_skills:
            enabled_skills.append(skill_name)
            self.config.set("enabled_skills", enabled_skills)
            core.config.save()
            msg = f"Skill '{skill_name}' has been enabled."
        else:
            msg = f"Skill '{skill_name}' is already enabled."

        if self.channel:
            self.channel.announce(msg)

    @core.module.command("skill disable", help="Disable a specific Addy Agent Skill.")
    async def disable_skill(self, skill_name: str):
        enabled_skills = self.config.get("enabled_skills") or []

        if skill_name in enabled_skills:
            enabled_skills.remove(skill_name)
            self.config.set("enabled_skills", enabled_skills)
            core.config.save()
            msg = f"Skill '{skill_name}' has been disabled."
        else:
            msg = f"Skill '{skill_name}' is not enabled."

        if self.channel:
            self.channel.announce(msg)

    async def on_system_prompt(self):
        """
        Injects the content of the enabled skills into the system prompt.
        """
        enabled_skills = self.config.get("enabled_skills") or []
        if not enabled_skills:
            return None

        skills_dir = self._get_skills_dir()
        prompts = []

        for skill in enabled_skills:
            skill_path = os.path.join(skills_dir, f"{skill}.md")
            if os.path.exists(skill_path):
                with open(skill_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    prompts.append(f"--- BEGIN SKILL: {skill} ---\n{content}\n--- END SKILL: {skill} ---")

        if prompts:
            return "\n\n".join(prompts)

        return None

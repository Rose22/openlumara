import os
import zipfile
import asyncio
from datetime import datetime
import core

class AutoBackup(core.module.Module):
    """
    Automatically backs up the OpenLumara data folder at a set interval
    """

    # -------------------------
    #   CONFIGURATION
    # -------------------------

    settings = {
        "backup_interval_days": {
            "description": "How often to perform a backup (in days). Set to 0 to disable automatic backups.",
            "type": "number",
            "default": 7
        },
        "backup_path": {
            "description": "The path where backup zip files will be stored.",
            "type": "string",
            "default": "data_backups"
        },
        "enable_notifications": {
            "description": "Whether to send a push notification after each backup.",
            "type": "boolean",
            "default": True
        }
    }

    # -------------------------
    #   EVENT HANDLERS
    # -------------------------

    async def on_ready(self):
        """Initialize the module and set up the backup scheduler."""
        self._backup_task = None
        self._interval_seconds = None
        self._last_backup = core.storage.StorageText("last_backup")
        self.backup_path = core.get_path(os.path.expanduser(self.config.get("backup_path")))

        await self._setup_backup()

    async def on_shutdown(self):
        """Cancel the background backup task."""
        if self._backup_task and not self._backup_task.done():
            self._backup_task.cancel()
            try:
                await self._backup_task
            except asyncio.CancelledError:
                pass

    async def on_background(self):
        """Main backup loop - runs in the background at configured intervals."""
        while True:
            try:
                interval = self.config.get("backup_interval_days")

                # If interval is 0, skip waiting (module is disabled)
                if not interval or interval <= 0:
                    await asyncio.sleep(60)  # Check periodically in case settings change
                    continue

                interval_seconds = interval * 86400  # convert days to seconds
                
                # Calculate how long to wait based on last backup time
                wait_time = await self._calculate_wait_time(interval_seconds)
                
                if wait_time > 0:
                    self.channel.log(self.name, f"Waiting {wait_time:.0f} seconds until next backup")
                    await asyncio.sleep(wait_time)

                # Check again after sleep in case settings changed
                interval = self.config.get("backup_interval_days")
                if not interval or interval <= 0:
                    continue

                # Perform the backup
                await self._perform_backup()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.channel.log(self.name, f"Error during backup cycle: {core.detail_error(e)}")
                # Wait a bit before retrying on error
                await asyncio.sleep(60)

    async def _setup_backup(self):
        """Set up the backup directory and log startup info."""
        # Create backup directory if it doesn't exist
        try:
            if not os.path.exists(self.backup_path):
                self.channel.log(self.name, f"Backup directory created: {self.backup_path}")
                os.makedirs(self.backup_path, exist_ok=True)
        except Exception as e:
            self.channel.log(self.name, f"Warning: Could not create backup directory '{self.backup_path}': {e}")

        interval = self.config.get("backup_interval_days", 7)
        if interval and interval > 0:
            self.channel.log(self.name, f"Automatic backups enabled every {interval} day(s)")
        else:
            self.channel.log(self.name, "Automatic backups are disabled (interval set to 0)")

    async def _perform_backup(self):
        """Perform a single backup operation."""
        enable_notifications = self.config.get("enable_notifications")
        data_folder = core.get_data_path()

        if not data_folder or not os.path.exists(data_folder):
            error_msg = f"Backup failed: Data folder not found.\n"
            self.channel.log(self.name, error_msg)
            if enable_notifications:
                await self.channel.push(
                    f"⚠️ Data Backup Failed\n{error_msg}"
                )
            return

        # Create the zip filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"openlumara_backup_{timestamp}.zip"
        zip_path = os.path.join(self.backup_path, zip_filename)

        try:
            # Create the zip backup
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(data_folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Calculate the archive name (relative to data folder)
                        arcname = os.path.relpath(file_path, data_folder)
                        zipf.write(file_path, arcname)

            # Get file size for notification
            file_size = os.path.getsize(zip_path)
            size_mb = file_size / (1024 * 1024)

            self.channel.log(self.name, f"Backup completed: {zip_filename} ({size_mb:.2f} MB)")

            # Send notification if enabled
            if enable_notifications:
                notification = (
                    f"✅ Data Backup Complete\n"
                    f"File: {zip_filename}\n"
                    f"Size: {size_mb:.2f} MB\n"
                    f"Location: {zip_path}"
                )
                await self.channel.push(notification)

            # Update last backup time in persistent storage
            self._last_backup.set(str(datetime.now().isoformat()))
            self.channel.log(self.name, f"Last backup time saved: {self._last_backup}")

        except Exception as e:
            error_msg = f"Backup failed with error: {e}"
            self.channel.log(self.name, error_msg)
            if enable_notifications:
                await self.channel.push(f"⚠️ Data Backup Failed\n{error_msg}")

    async def _calculate_wait_time(self, interval_seconds):
        """
        Calculate how long to wait before the next backup.
        
        Takes into account when the last backup was performed and only waits
        for the remaining time needed to meet the configured interval.
        
        Args:
            interval_seconds: The full interval in seconds
            
        Returns:
            The number of seconds to wait (0 if backup is due immediately)
        """
        # Try to get the last backup timestamp
        last_backup_str = str(self._last_backup)
        
        if not last_backup_str or last_backup_str == "None" or last_backup_str == "":
            # No previous backup exists, wait for full interval
            self.channel.log(self.name, "No previous backup found, performing initial backup.")
            return 0
        
        try:
            last_backup_time = datetime.fromisoformat(last_backup_str)
            elapsed = (datetime.now() - last_backup_time).total_seconds()
            remaining = interval_seconds - elapsed
            
            if remaining <= 0:
                self.channel.log(self.name, "Backup interval has passed, backing up immediately")
                return 0
            
            self.channel.log(self.name, f"Last backup was {elapsed:.0f}s ago, {remaining:.0f}s remaining until next backup")
            return remaining
            
        except (ValueError, TypeError) as e:
            # Invalid timestamp format, wait for full interval
            self.channel.log(self.name, f"Invalid last backup timestamp: {e}, waiting full interval")
            return interval_seconds

    # -------------------------
    #   AI TOOLS
    # -------------------------

    async def get_backup_status(self):
        """
        Get the current backup configuration and last backup status.

        Returns current settings and when the last backup was performed.
        """
        interval = self.config.get("backup_interval_days")
        enable_notifications = self.config.get("enable_notifications")
        data_folder = core.get_data_path()

        # Get list of existing backups
        try:
            existing_backups = []
            if os.path.exists(self.backup_path):
                for f in os.listdir(self.backup_path):
                    if f.endswith('.zip') and f.startswith('openlumara_backup_'):
                        file_path = os.path.join(self.backup_path, f)
                        size = os.path.getsize(file_path)
                        size_mb = size / (1024 * 1024)
                        mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        existing_backups.append({
                            "filename": f,
                            "size_mb": round(size_mb, 2),
                            "modified": mod_time.strftime("%Y-%m-%d %H:%M:%S")
                        })
            # Sort by modification time, newest first
            existing_backups.sort(key=lambda x: x["modified"], reverse=True)
        except Exception as e:
            existing_backups = [{"error": str(e)}]

        status = {
            "backup_interval_days": interval,
            "backup_path": self.backup_path,
            "enable_notifications": enable_notifications,
            "data_folder_path": data_folder or "default (auto-detected)",
            "last_backup": datetime.fromisoformat(str(self._last_backup)).strftime("%Y-%m-%d %H:%M:%S") if str(self._last_backup) and str(self._last_backup) != "None" else "Never",
            "existing_backups_count": len(existing_backups),
            "existing_backups": existing_backups[:5]  # Show last 5 backups
        }

        return self.result(status, success=True)

    # -------------------------
    #   USER-FACING COMMANDS
    # -------------------------

    @core.module.command("backup", help={
        "": "Shows the current backup status and configuration",
        "trigger": "Manually trigger an immediate backup"
    })
    async def backup_command(self, args: list):
        if not args or args[0] != "trigger":
            status = await self.get_backup_status()
            return status
        else:
            result = await self._perform_backup()
            return self.result("Manual backup triggered successfully!", success=True)

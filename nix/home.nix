{
  config,
  lib,
  ...
}:

let
  cfg = config.services.openlumara;
  inherit (lib) mkIf mkOption types;

  settingsToArgs = import ./settings.nix { inherit lib; };

  # the install dir is read-only, so the docs module's user folder goes to the
  # state dir; `openlumara_docs` is the bundled guide and stays in the package
  defaultSettings = {
    modules.settings.docs.folders = [ "openlumara_docs" "~/.openlumara/docs" ];
  };
in
{
  options.services.openlumara = {
    enable = lib.mkEnableOption "OpenLumara AI agent framework as a user service";

    package = mkOption {
      type = types.package;
      description = ''
        The openlumara package to run. The flake's `homeModules` sets this to
        the matching `pkgs.openlumara`, so it only needs to be set when
        importing this module directly.
      '';
    };

    settings = mkOption {
      type = types.attrsOf types.anything;
      default = { };
      description = ''
        Settings passed as CLI overrides on every start, nested by section, e.g.
        `settings.channels.settings.webui = { network_mode = "internet"; port = 3000; };`.

        Values are passed as `--<dotted.key> <value>`; object-valued settings cannot be
        passed this way. Secrets do not belong here (the store is world readable);
        put them in `~/.openlumara/config.yml` or in {option}`environmentFile`.
      '';
      example = lib.literalExpression ''
        {
          channels.settings.webui = {
            network_mode = "internet";
            port = 3000;
          };
        }
      '';
    };

    environmentFile = mkOption {
      type = types.nullOr types.path;
      default = null;
      description = "Environment file loaded by the service, e.g. for API keys.";
    };

    extraArgs = mkOption {
      type = types.listOf types.str;
      default = [ ];
      description = "Extra command line arguments for openlumara.";
    };
  };

  config = mkIf cfg.enable {
    home.packages = [ cfg.package ];

    systemd.user.services.openlumara = {
      Unit.Description = "OpenLumara AI agent framework";

      Service = {
        ExecStart = lib.escapeShellArgs (
          [ "${cfg.package}/bin/openlumara" ]
          ++ settingsToArgs "" (lib.recursiveUpdate defaultSettings cfg.settings)
          ++ cfg.extraArgs
        );
        Restart = "on-failure";
        RestartSec = 5;
      }
      // lib.optionalAttrs (cfg.environmentFile != null) {
        EnvironmentFile = cfg.environmentFile;
      };

      Install.WantedBy = [ "default.target" ];
    };
  };
}

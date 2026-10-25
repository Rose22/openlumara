{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.openlumara;
  inherit (lib) mkIf mkOption types;

  # flatten `settings` into dotted CLI overrides:
  # { channels.settings.webui = { port = 3000; }; } -> --channels.settings.webui.port 3000
  settingsToArgs =
    prefix: attrs:
    lib.concatLists (
      lib.mapAttrsToList (
        name: value:
        let
          key = if prefix == "" then name else "${prefix}.${name}";
        in
        if lib.isAttrs value then
          settingsToArgs key value
        else if value == null then
          [ ]
        else if lib.isBool value then
          [
            "--${key}"
            (lib.boolToString value)
          ]
        else if lib.isList value then
          lib.optional (value != [ ]) [
            "--${key}"
            (lib.concatMapStringsSep "," toString value)
          ]
        else
          [
            "--${key}"
            (toString value)
          ]
      ) attrs
    );
in
{
  options.services.openlumara = {
    enable = lib.mkEnableOption "OpenLumara AI agent framework";

    package = mkOption {
      type = types.package;
      description = ''
        The openlumara package to run. The flake's `nixosModules` sets this to
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
        passed this way. Secrets do not belong here (the unit and store are world
        readable); put them in `config.yml` under the state directory or in
        {option}`environmentFile`.
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
    users.users.openlumara = {
      isSystemUser = true;
      group = "openlumara";
      home = "/var/lib/openlumara";
    };
    users.groups.openlumara = { };

    systemd.services.openlumara = {
      description = "OpenLumara AI agent framework";
      wantedBy = [ "multi-user.target" ];
      wants = [ "network-online.target" ];
      after = [ "network-online.target" ];

      environment.OPENLUMARA_HOME = "/var/lib/openlumara";

      serviceConfig = {
        ExecStart = lib.escapeShellArgs (
          [ "${cfg.package}/bin/openlumara" ] ++ settingsToArgs "" cfg.settings ++ cfg.extraArgs
        );
        User = "openlumara";
        Group = "openlumara";
        StateDirectory = "openlumara";
        StateDirectoryMode = "0700";
        WorkingDirectory = "/var/lib/openlumara";
        Restart = "on-failure";
        RestartSec = 5;

        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        NoNewPrivileges = true;
      }
      // lib.optionalAttrs (cfg.environmentFile != null) {
        EnvironmentFile = cfg.environmentFile;
      };
    };
  };
}

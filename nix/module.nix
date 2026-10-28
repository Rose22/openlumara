{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.openlumara;
  inherit (lib) mkIf mkOption types;

  settingsToArgs = import ./settings.nix { inherit lib; };

  # the install dir is read-only, so the docs module's user folder goes to the
  # state dir; `openlumara_docs` is the bundled guide and stays in the package
  defaultSettings = {
    modules.settings.docs.folders = [ "openlumara_docs" "/var/lib/openlumara/docs" ];
  };

  extraPackagesList = cfg.extraPackages pkgs.python313.pkgs;
  extraPython = pkgs.python313.withPackages cfg.extraPackages;
  extraSitePackages = "${extraPython}/${pkgs.python313.sitePackages}";
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

    enableDynamicDeps = mkOption {
      type = types.bool;
      default = false;
      description = ''
        Allow OpenLumara to install module/channel dependencies at runtime into
        `OPENLUMARA_HOME/module_deps`. Runtime installs are not reproducible and
        binary wheels need nix-ld or an FHS environment; pure-Python packages work.
        Prefer `extraPackages` for reproducible dependencies.
      '';
    };

    extraPackages = mkOption {
      type = types.functionTo (types.listOf types.package);
      default = _: [ ];
      description = ''
        Python packages from nixpkgs made available to modules and channels.
        Receives the nixpkgs Python package set, e.g. `ps: [ ps.discordpy ]`.
        They are appended after the bundled environment, so bundled versions win.
      '';
      example = lib.literalExpression "ps: [ ps.discordpy ps.beautifulsoup4 ]";
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

      environment = {
        OPENLUMARA_HOME = "/var/lib/openlumara";
      } // lib.optionalAttrs (extraPackagesList != [ ]) {
        OPENLUMARA_EXTRA_SITE_PACKAGES = extraSitePackages;
      };

      serviceConfig = {
        ExecStart = lib.escapeShellArgs (
          [ "${cfg.package}/bin/openlumara" ]
          ++ lib.optional (!cfg.enableDynamicDeps) "--disable_auto_installer"
          ++ settingsToArgs "" (lib.recursiveUpdate defaultSettings cfg.settings)
          ++ cfg.extraArgs
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

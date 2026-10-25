{
  description = "OpenLumara - modular, token-efficient, local-first AI agent framework";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      pyproject-nix,
      uv2nix,
      pyproject-build-systems,
      home-manager,
      ...
    }:
    let
      inherit (nixpkgs) lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = lib.genAttrs systems;

      # every bundled non-GUI extra: the Qt GUI needs PySide6, which stays opt-in
      packageExtras = [
        "webui"
        "channels"
        "modules"
      ];

      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

      pythonSetFor =
        pkgs:
        let
          python = pkgs.python313;
          base = pkgs.callPackage pyproject-nix.build.packages { inherit python; };
        in
        base.overrideScope (
          lib.composeManyExtensions [
            pyproject-build-systems.overlays.wheel
            (workspace.mkPyprojectOverlay {
              sourcePreference = "wheel";
              dependencies = { openlumara = packageExtras; };
            })
          ]
        );

      venvFor = pkgs: (pythonSetFor pkgs).mkVirtualEnv "openlumara-env" { openlumara = packageExtras; };
      # both names are in the wild: homeModules is the newer convention
      homeModuleSet = rec {
        openlumara =
          { lib, pkgs, ... }:
          {
            imports = [ ./nix/home.nix ];
            services.openlumara.package = lib.mkDefault self.packages.${pkgs.stdenv.hostPlatform.system}.default;
          };
        default = openlumara;
      };
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          openlumara = pkgs.callPackage ./nix/package.nix {
            src = self;
            venv = venvFor pkgs;
          };
        in
        {
          inherit openlumara;
          default = openlumara;
        }
      );

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/openlumara";
        };
      });

      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.python313
              pkgs.uv
            ];
            shellHook = ''
              unset PYTHONPATH
              export UV_PYTHON=${pkgs.python313}/bin/python
              export UV_PYTHON_DOWNLOADS=never
              # same extras as the package; add the Qt GUI with
              # `uv sync --inexact --extra gui` when working on that channel
              uv sync --frozen --inexact --extra webui --extra channels --extra modules
              source .venv/bin/activate
            '';
          };
        }
      );

      checks = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          package = self.packages.${system}.default;
          venv = venvFor pkgs;

          nixosEval = lib.nixosSystem {
            inherit system;
            modules = [
              self.nixosModules.default
              {
                system.stateVersion = "26.05";
                services.openlumara = {
                  enable = true;
                  settings.channels.settings.webui = {
                    network_mode = "internet";
                    port = 3000;
                  };
                };
              }
            ];
          };

          service = nixosEval.config.systemd.services.openlumara;
          execStart = service.serviceConfig.ExecStart;
          execStartText = if lib.isList execStart then lib.concatStringsSep " " execStart else execStart;
          overrides = "--channels.settings.webui.network_mode internet --channels.settings.webui.port 3000";
          serviceHome = service.environment.OPENLUMARA_HOME;
          userHome = nixosEval.config.users.users.openlumara.home;

          homeEval = home-manager.lib.homeManagerConfiguration {
            pkgs = nixpkgs.legacyPackages.${system};
            modules = [
              self.homeModules.default
              {
                home.username = "openlumara";
                home.homeDirectory = "/home/openlumara";
                home.stateVersion = "26.05";
                services.openlumara = {
                  enable = true;
                  settings.channels.settings.webui = {
                    network_mode = "internet";
                    port = 3000;
                  };
                };
              }
            ];
          };

          userService = homeEval.config.systemd.user.services.openlumara;
          userExecStart = userService.Service.ExecStart;
          userExecStartText = if lib.isList userExecStart then lib.concatStringsSep " " userExecStart else userExecStart;
        in
        {
          openlumara = package;

          requirements = pkgs.runCommand "openlumara-requirements" {
            nativeBuildInputs = [ pkgs.python313 ];
          } ''
            python ${self}/tools/dump_requirements.py --check
            touch $out
          '';

          smoke = pkgs.runCommand "openlumara-smoke" {
            nativeBuildInputs = [ venv ];
          } ''
            export HOME=$TMPDIR
            export OPENLUMARA_HOME=$TMPDIR/state
            export PYTHONPATH=${self}''${PYTHONPATH:+:$PYTHONPATH}

            python -c 'import fastapi, starlette, uvicorn, itsdangerous, websockets, jinja2, markupsafe, multipart, aiohttp, bs4, ddgs, tree_sitter_language_pack, flask, werkzeug, discord, telegram, nio, vodozemac, mcp, simpleeval, prompt_toolkit, rich, msgpack, yaml, json_repair, partial_json_parser, regex, pypdf, ulid'

            python -c 'import os, core, core.config; core.config.load(); assert core.get_home() == os.path.realpath(os.environ["OPENLUMARA_HOME"]); assert core.get_path() != core.get_home()'

            for entry in config.yml data user_modules user_channels .module_cache.json; do
              test -e "$OPENLUMARA_HOME/$entry"
            done

            test ! -e ${self}/config.yml
            ${package}/bin/openlumara --help > /dev/null
            touch $out
          '';

          nixos-module =
            if lib.hasInfix overrides execStartText then
              if userHome == "/var/lib/openlumara" then
                if serviceHome == "/var/lib/openlumara" then
                  pkgs.runCommand "openlumara-nixos-module" { } "touch $out"
                else
                  throw "services.openlumara: unexpected OPENLUMARA_HOME ${toString serviceHome}"
              else
                throw "services.openlumara: unexpected user home ${userHome}"
            else
              throw "services.openlumara: ExecStart is missing the settings overrides: ${execStartText}";

          home-manager =
            if lib.hasInfix overrides userExecStartText then
              if lib.elem "default.target" (userService.Install.WantedBy or [ ]) then
                pkgs.runCommand "openlumara-home-manager" { } "touch $out"
              else
                throw "homeModules.openlumara: the user service is not wanted by default.target"
            else
              throw "homeModules.openlumara: ExecStart is missing the settings overrides: ${userExecStartText}";
        }
      );

      nixosModules = rec {
        openlumara =
          { lib, pkgs, ... }:
          {
            imports = [ ./nix/module.nix ];
            services.openlumara.package = lib.mkDefault self.packages.${pkgs.stdenv.hostPlatform.system}.default;
          };
        default = openlumara;
      };

      homeModules = homeModuleSet;
      homeManagerModules = homeModuleSet;

      overlays.default = final: _prev: {
        openlumara = final.callPackage ./nix/package.nix {
          src = self;
          venv = venvFor final;
        };
      };
    };
}

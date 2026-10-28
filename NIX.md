# Nix

OpenLumara ships a flake with the app package, a NixOS module, a home-manager module and a dev shell. Everything is pinned to a stable nixpkgs (`nixos-26.05`), and the Python environment is built from `uv.lock` with [uv2nix](https://github.com/pyproject-nix/uv2nix).

## Running it

```sh
nix run github:Rose22/openlumara
```

```sh
nix build github:Rose22/openlumara    # ./result/bin/openlumara
nix develop github:Rose22/openlumara  # python + uv, with .venv synced from uv.lock
nix flake check github:Rose22/openlumara
```

The package includes the WebUI, CLI, Telegram, Discord, Matrix and module dependencies. The Qt GUI channel is not included (it needs PySide6), so leave the `gui` channel disabled. Module dependency handling is described in [Module dependencies](#module-dependencies).

## State and config

OpenLumara keeps `config.yml`, `data/`, `user_modules/`, `user_channels/`, `module_deps/` and the module cache in `OPENLUMARA_HOME`. Bundled files (WebUI assets, docs, templates, built-in themes) are read from the package and never written to.

`nix run` and the package use the app default, `~/.openlumara`. The NixOS module sets it to `/var/lib/openlumara`.

Both modules also default `modules.settings.docs.folders` to the bundled `openlumara_docs` guide plus a writable `docs` folder in the state directory (`/var/lib/openlumara/docs`, or `~/.openlumara/docs` under home-manager). Override it with `services.openlumara.settings.modules.settings.docs.folders`, and point extra docs folders at absolute paths (or `~` ones), since the package directory is read-only.

## Module dependencies

Bundled module/channel dependencies are declared in `pyproject.toml` and included in the package. User-installed modules and channels can declare extra dependencies; with runtime installation enabled they go to `OPENLUMARA_HOME/module_deps/<section>/<name>` and are appended after the bundled environment, so bundled versions win.

On NixOS and home-manager the declarative option is preferred:

```nix
services.openlumara.extraPackages = ps: [ ps.discordpy ];
```

`extraPackages` builds a `python313.withPackages` environment and appends it after the bundled environment. To allow runtime installs instead, set:

```nix
services.openlumara.enableDynamicDeps = true;
```

Runtime installs are not reproducible and only pure-Python packages are reliable; binary wheels need `programs.nix-ld.enable` or an FHS environment. The option is off by default for the service modules; `nix run` and the bare package allow it.

## NixOS

The module runs the app as an `openlumara` system user with `/var/lib/openlumara` as its state directory. Options:

| Option | Description |
| --- | --- |
| `services.openlumara.enable` | Start the service |
| `services.openlumara.package` | Package to run; the flake sets it to the matching `pkgs.openlumara` |
| `services.openlumara.settings` | Nested settings passed as dotted CLI overrides |
| `services.openlumara.environmentFile` | Environment file loaded by the unit |
| `services.openlumara.extraArgs` | Extra command line arguments |
| `services.openlumara.enableDynamicDeps` | Allow runtime module dependency installs (default `false`) |
| `services.openlumara.extraPackages` | Python packages from nixpkgs for modules/channels, e.g. `ps: [ ps.discordpy ];` |

`settings` is flattened into flags, so `settings.channels.settings.webui.port = 3000;` becomes `--channels.settings.webui.port 3000`. Values can be strings, numbers, booleans or lists; nested attrsets are flattened further. They are applied on every start, which means the WebUI's saved settings win during a session but these keys get re-applied on the next one. Leave secrets out of `settings` (the unit and store are world readable) and use `config.yml` in the state directory, or `environmentFile` for anything the app reads from the environment.

Example `flake.nix` for a host:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    openlumara.url = "github:Rose22/openlumara";
  };

  outputs = { nixpkgs, openlumara, ... }: {
    nixosConfigurations.myhost = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        openlumara.nixosModules.default
        ({ pkgs, ... }: {
          services.openlumara = {
            enable = true;
            settings.channels.settings.webui = {
              network_mode = "internet";
              port = 3000;
            };
          };

          networking.firewall.allowedTCPPorts = [ 3000 ];
        })
      ];
    };
  };
}
```

Apply it with `nixos-rebuild switch --flake .#myhost`, then open the WebUI on port 3000 and set up the API connection there. The config file it writes lives at `/var/lib/openlumara/config.yml`.

```sh
systemctl status openlumara
journalctl -u openlumara -f
```

If you don't use flakes for your system config, the package is also available as `overlays.default`, which adds `pkgs.openlumara`.

## home-manager

`homeModules.default` (also exposed as `homeManagerModules.default`) runs OpenLumara as a systemd user service. It takes the same `enable`, `package`, `settings`, `environmentFile`, `extraArgs`, `enableDynamicDeps` and `extraPackages` options as the NixOS module, adds the package to `home.packages`, and installs the unit into `default.target`. State goes to `~/.openlumara`.

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    openlumara.url = "github:Rose22/openlumara";
  };

  outputs = { nixpkgs, home-manager, openlumara, ... }: {
    nixosConfigurations.myhost = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        home-manager.nixosModules.home-manager
        {
          home-manager.useGlobalPkgs = true;
          home-manager.useUserPackages = true;

          home-manager.users.me = {
            imports = [ openlumara.homeModules.default ];

            home.stateVersion = "26.05";
            services.openlumara = {
              enable = true;
              settings.channels.settings.webui.port = 3000;
            };
          };
        }
      ];
    };
  };
}
```

```sh
systemctl --user status openlumara
journalctl --user -u openlumara -f
```

The WebUI stays on localhost with the default `network_mode`; to reach it from another machine, set `network_mode = "internet"` and open the port in the system firewall (`networking.firewall.allowedTCPPorts`), which home-manager cannot do for you.

A user service only starts at boot with lingering enabled: `users.users.me.linger = true;` in the system config, or `loginctl enable-linger me`.

Don't enable both the NixOS and the home-manager module — you'd get two instances fighting over the same WebUI port. Pick one.

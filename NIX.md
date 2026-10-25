# Nix

OpenLumara ships a flake with the app package, a NixOS module and a dev shell. Everything is pinned to a stable nixpkgs (`nixos-26.05`), and the Python environment is built from `uv.lock` with [uv2nix](https://github.com/pyproject-nix/uv2nix).

## Running it

```sh
nix run github:Rose22/openlumara
```

```sh
nix build github:Rose22/openlumara    # ./result/bin/openlumara
nix develop github:Rose22/openlumara  # python + uv, with .venv synced from uv.lock
nix flake check github:Rose22/openlumara
```

The package includes the WebUI, CLI, Telegram, Discord, Matrix and module dependencies. The Qt GUI channel is not included (it needs PySide6), so leave the `gui` channel disabled. Module dependency auto-install is disabled too, since the environment is immutable.

## State and config

OpenLumara keeps `config.yml`, `data/`, `user_modules/`, `user_channels/` and the module cache in `OPENLUMARA_HOME`. Bundled files (WebUI assets, docs, templates, built-in themes) are read from the package and never written to.

`nix run` and the package use the app default, `~/.openlumara`. The NixOS module sets it to `/var/lib/openlumara`.

## NixOS

The module runs the app as an `openlumara` system user with `/var/lib/openlumara` as its state directory. Options:

| Option | Description |
| --- | --- |
| `services.openlumara.enable` | Start the service |
| `services.openlumara.package` | Package to run; the flake sets it to the matching `pkgs.openlumara` |
| `services.openlumara.settings` | Nested settings passed as dotted CLI overrides |
| `services.openlumara.environmentFile` | Environment file loaded by the unit |
| `services.openlumara.extraArgs` | Extra command line arguments |

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

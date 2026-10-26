# flatten nested settings into dotted CLI overrides:
# { channels.settings.webui = { port = 3000; }; } -> --channels.settings.webui.port 3000
{ lib }:

let
  flatten =
    prefix: attrs:
    lib.concatLists (
      lib.mapAttrsToList (
        name: value:
        let
          key = if prefix == "" then name else "${prefix}.${name}";
        in
        if lib.isAttrs value then
          flatten key value
        else if value == null then
          [ ]
        else if lib.isBool value then
          [
            "--${key}"
            (lib.boolToString value)
          ]
        else if lib.isList value then
          lib.optionals (value != [ ]) [
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
flatten

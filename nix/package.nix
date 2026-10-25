{ lib, stdenv, makeWrapper, src, venv }:

stdenv.mkDerivation {
  pname = "openlumara";
  version = "1.0";

  inherit src;

  nativeBuildInputs = [ makeWrapper ];

  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall

    mkdir -p $out/share/openlumara $out/bin
    cp -r core modules channels openlumara_docs main.py pyproject.toml $out/share/openlumara/

    makeWrapper ${venv}/bin/python $out/bin/openlumara \
      --prefix PYTHONPATH : "$out/share/openlumara" \
      --add-flags "$out/share/openlumara/main.py" \
      --add-flags "--disable_auto_installer" \
      --run 'export OPENLUMARA_HOME="''${OPENLUMARA_HOME:-''${XDG_DATA_HOME:-$HOME/.local/share}/openlumara}"'

    runHook postInstall
  '';

  meta = {
    description = "Modular, token-efficient, local-first AI agent framework";
    homepage = "https://github.com/Rose22/openlumara";
    license = lib.licenses.gpl2Plus;
    mainProgram = "openlumara";
    platforms = lib.platforms.linux;
  };
}

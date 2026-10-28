{ lib, stdenv, makeWrapper, uv, src, venv }:

stdenv.mkDerivation {
  pname = "openlumara";
  version = "1.0";

  inherit src;

  nativeBuildInputs = [ makeWrapper uv ];

  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall

    mkdir -p $out/share/openlumara $out/bin
    cp -r core modules channels openlumara_docs main.py pyproject.toml $out/share/openlumara/

    makeWrapper ${venv}/bin/python $out/bin/openlumara \
      --prefix PATH : ${lib.makeBinPath [ uv ]} \
      --set UV_PYTHON_DOWNLOADS never \
      --set VIRTUAL_ENV ${venv} \
      --prefix PYTHONPATH : "$out/share/openlumara" \
      --add-flags "$out/share/openlumara/main.py"

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

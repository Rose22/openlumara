# AI Written: Claude Opus 5.5
raise RuntimeError("must not be imported while dependencies are missing")


class BadDeps:
    dependencies = ["openlumara-test-missing-package>=1.0", "pytest[testing]==1.0"]

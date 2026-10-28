# termux-packages recipe for python-cffi (not in the Termux repository).
# Derived from the recipe embedded in deniscerri/ytdlnis-packages scripts/build_python.sh (GPL-3.0).
# @VERSION@, @URL@ and @SHA256@ are filled from inputs.lock (cffi_sdist) by scripts/build_native.sh.
TERMUX_PKG_HOMEPAGE=https://cffi.readthedocs.io/
TERMUX_PKG_DESCRIPTION="Foreign Function Interface for Python calling C code"
TERMUX_PKG_LICENSE="MIT"
TERMUX_PKG_LICENSE_FILE="LICENSE"
TERMUX_PKG_MAINTAINER="indirdim-runtime"
TERMUX_PKG_VERSION="@VERSION@"
TERMUX_PKG_SRCURL="@URL@"
TERMUX_PKG_SHA256=@SHA256@
TERMUX_PKG_DEPENDS="libffi, python, python-pip"
TERMUX_PKG_SETUP_PYTHON=true
TERMUX_PKG_BUILD_IN_SRC=true

termux_step_pre_configure() {
	LDFLAGS+=" -Wl,--no-as-needed -lpython${TERMUX_PYTHON_VERSION}"
}

termux_step_make() {
	:
}

termux_step_make_install() {
	PYTHONDONTWRITEBYTECODE=1 pip install . --prefix="$TERMUX_PREFIX" -vv --no-build-isolation --no-deps --no-compile
}

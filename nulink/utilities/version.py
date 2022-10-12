def check_version(to_checked_version: str) -> object:
    # version: major.minor.mini

    from nulink import __version__

    version: list = (to_checked_version or '0.1.0').split(".")
    cur_version: list = __version__.split('.')
    if cur_version[0] != version[0] or cur_version[1] != version[1]:
        return False

    return True


class VersionMismatchError(RuntimeError):
    pass


check_version_pickle_symbol = ">>__checkout_version__<<"

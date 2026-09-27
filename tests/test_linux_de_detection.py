from now_playing_desktops.platforms.linux_de import (
    LinuxDesktopEnvironment,
    detect_linux_desktop_environment,
)


def test_detect_gnome_from_xdg_current_desktop():
    de = detect_linux_desktop_environment(env_tokens={"gnome"}, process_names=set())
    assert de == LinuxDesktopEnvironment.GNOME


def test_detect_gnome_unity_budgie_cinnamon_tokens():
    for token in ("unity", "budgie:gnome", "cinnamon-session"):
        de = detect_linux_desktop_environment(env_tokens={token}, process_names=set())
        assert de == LinuxDesktopEnvironment.GNOME


def test_detect_kde_from_plasmashell_process():
    de = detect_linux_desktop_environment(
        env_tokens=set(),
        process_names={"plasmashell", "systemd"},
    )
    assert de == LinuxDesktopEnvironment.KDE


def test_detect_kde_from_xdg_token():
    de = detect_linux_desktop_environment(env_tokens={"kde"}, process_names=set())
    assert de == LinuxDesktopEnvironment.KDE


def test_detect_other_when_no_known_signals():
    de = detect_linux_desktop_environment(env_tokens={"i3"}, process_names={"i3"})
    assert de == LinuxDesktopEnvironment.OTHER

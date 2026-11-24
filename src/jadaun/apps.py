from django.apps import AppConfig


class JadaunConfig(AppConfig):
    name = "jadaun"
    label = "jadaun"
    verbose_name = "jadaun"

    def ready(self) -> None:
        from django.conf import settings

        builder = getattr(settings, "JADAUN_BUILDER", None)
        if builder is None:
            # autowire() wasn't used (e.g. the manual Initializer/Builder
            # wiring path, or jadaun added to INSTALLED_APPS by hand) -
            # nothing for us to mount.
            return

        from jadaun.autowire import mount_combined_urlconf

        api_prefix = getattr(settings, "JADAUN_API_PREFIX", "api/")
        root_urlconf = getattr(settings, "ROOT_URLCONF", "") or None
        settings.ROOT_URLCONF = mount_combined_urlconf(root_urlconf, builder, api_prefix)

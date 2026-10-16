"""Shared admission and completion rules for synchronous competitor collectors."""
from datasets.services.parsers.queue_execution import standalone
from datasets.services.parsers.product_image_sync import sync_iprice_product_images


def collect_competitor(source, *, workspace, limit=None, workers=1, sync_links=False):
    from datasets.services.parsers.ps_links import sync_ps_product_urls
    from datasets.services.parsers.ps_product_parser import parse_ps_products
    from datasets.services.parsers.tt_links import sync_tt_product_urls
    from datasets.services.parsers.tt_product_parser import parse_tt_products

    collectors = {"ps": (sync_ps_product_urls, parse_ps_products), "tt": (sync_tt_product_urls, parse_tt_products)}
    if source not in collectors or workspace.code != "select-market":
        raise ValueError("Unsupported competitor workspace or source")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    if not 1 <= workers <= 4:
        raise ValueError("workers must be between 1 and 4")
    links_loader, products_loader = collectors[source]

    @standalone(source)
    def execute(*, workspace):
        links = links_loader(workspace=workspace) if sync_links else None
        result = products_loader(workspace=workspace, limit=limit, workers=workers)
        images = sync_iprice_product_images(source=source, workspace=workspace)
        if result["failed"]:
            raise RuntimeError(f"{source.upper()} collection incomplete: {result}")
        return {"links": links, "products": result, "images": images}

    return execute(workspace=workspace)

import logging
from typing import Any

from graphene import Connection, Int

logger = logging.getLogger(__name__)


class PdfPageAwareConnection(Connection):
    class Meta:
        abstract = True

    current_page = Int()
    page_count = Int()

    def resolve_current_page(root, info, **kwargs) -> Any:
        # print(
        #     f"PdfPageAwareConnection- resolve_total_count kwargs: {kwargs} / root {dir(root)} / iteracble "
        #     f"{root.iterable.count()}"
        # )
        return 1

    def resolve_page_count(root, info, **kwargs) -> Any:

        largest_page_number = max(
            list(root.iterable.values_list("page", flat=True).distinct())
        )
        # print(f"Unique page list: {largest_page_number}")

        # print(f"PdfPageAwareConnection - resolve_edge_count kwargs: {kwargs}")
        return largest_page_number

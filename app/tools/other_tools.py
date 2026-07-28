import re
import requests
from langchain.tools import tool
import logging

from app.utils.common import _merge_auth_headers

logger = logging.getLogger(__name__)


@tool
def get_data_from_link(
    url: str, headers: dict | None = None, params: dict | None = None
):
    """Fetch content from a link and return a summary or error details."""

    logger.info(f"Retrieving data from link: {url}")
    try:
        response = requests.get(
            url,
            headers=_merge_auth_headers(headers),
            params=params,
            timeout=15,
        )
        response.raise_for_status()

        content_type = (
            response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        )

        if (
            content_type == ""
            or content_type.startswith("text/")
            or content_type
            in (
                "application/json",
                "application/xml",
                "application/xhtml+xml",
            )
        ):
            if "application/json" in content_type:
                data = response.json()
                return {
                    "url": url,
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "data": data,
                }

            text = response.text
            snippet = " ".join(text.strip().split())[:2000]
            result = {
                "url": url,
                "status_code": response.status_code,
                "content_type": content_type,
                "snippet": snippet,
            }

            if "html" in content_type:
                title_match = re.search(
                    r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL
                )
                if title_match:
                    result["title"] = title_match.group(1).strip()

            return result

        return {
            "url": url,
            "status_code": response.status_code,
            "content_type": content_type,
            "content_length": len(response.content),
            "message": "Retrieved non-text content. Use a browser or a specialized parser for details.",
        }
    except requests.RequestException as error:
        logger.warning(f"Failed to retrieve link {url}: {error}")
        return {
            "url": url,
            "error": str(error),
            "message": "The link could not be retrieved. It may be broken, blocked, or the content could not be parsed.",
        }

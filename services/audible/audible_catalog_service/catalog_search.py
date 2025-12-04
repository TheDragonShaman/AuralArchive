import logging
from typing import Any, Dict, List, Optional

import requests

from .error_handling import error_handler


class AudibleSearch:
    """Handles Audible API search operations and requests."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("AudibleService.Search")
        self.base_url = "https://api.audible.com/1.0/catalog/products"
        self.session = self._setup_session()

    def _setup_session(self) -> requests.Session:
        """Configure a requests session with the headers Audible expects."""

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36"
                )
            }
        )
        return session

    @error_handler.with_retry(max_retries=3, retry_delay=1.0)
    def search_books(self, query: str, region: str = "us", num_results: int = 25) -> List[Dict[str, Any]]:
        """Search for books on Audible by keyword."""

        self.logger.info("Searching Audible for: %s", query)

        try:
            params = self._build_search_params(query=query, num_results=num_results, region=region)
            error_handler.log_request_info(self.base_url, params, f"Search books: {query}")

            response = self.session.get(self.base_url, params=params, timeout=30)
            if not error_handler.validate_response(response, f"Search books: {query}"):
                return []

            error_handler.handle_api_quota(response)

            api_data = response.json()
            products = api_data.get("products", [])

            self.logger.info("Found %s books for query '%s'", len(products), query)
            return products

        except requests.exceptions.RequestException as exc:
            self.logger.error("Request error while searching for '%s': %s", query, exc)
            raise
        except Exception as exc:  # noqa: BLE001 - surface unexpected issues
            self.logger.error("Unexpected error while searching for '%s': %s", query, exc)
            raise

    @error_handler.with_retry(max_retries=3, retry_delay=1.0)
    def get_book_details(self, asin: str, region: str = "us") -> Optional[Dict[str, Any]]:
        """Retrieve detailed information for a specific ASIN."""

        self.logger.info("Retrieving details for ASIN: %s", asin)

        try:
            params = self._build_details_params(asin=asin, region=region)
            error_handler.log_request_info(self.base_url, params, f"Get book details: {asin}")

            response = self.session.get(self.base_url, params=params, timeout=30)
            if not error_handler.validate_response(response, f"Get book details: {asin}"):
                return None

            error_handler.handle_api_quota(response)

            api_data = response.json()
            products = api_data.get("products", [])
            if not products:
                self.logger.warning("No product returned for ASIN: %s", asin)
                return None

            product = products[0]
            returned_asin = product.get("asin")
            if returned_asin and returned_asin != asin:
                self.logger.warning("ASIN mismatch. Requested %s but received %s", asin, returned_asin)

            return product

        except requests.exceptions.RequestException as exc:
            self.logger.error("Request error while fetching ASIN '%s': %s", asin, exc)
            raise
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Unexpected error while fetching ASIN '%s': %s", asin, exc)
            raise

    def _build_search_params(self, query: str, num_results: int, region: str) -> Dict[str, str]:
        """Build query parameters for keyword search requests."""

        return {
            "response_groups": "contributors,product_attrs,product_desc,product_extended_attrs,series,rating,media,relationships,customer_rights",
            "num_results": str(num_results),
            "products_sort_by": "Relevance",
            "keywords": query,
            "marketplace": region,
        }

    def _build_details_params(self, asin: str, region: str) -> Dict[str, str]:
        """Build query parameters for the details endpoint."""

        return {
            "response_groups": "contributors,product_attrs,product_desc,product_extended_attrs,series,rating,reviews,media,relationships,customer_rights",
            "asin": asin,
            "marketplace": region,
        }

    @error_handler.with_retry(max_retries=3, retry_delay=1.0)
    def search_by_author(
        self,
        author: str,
        region: str = "us",
        num_results: int = 25,
        response_groups: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for books using Audible's author filter."""

        self.logger.info("Searching Audible for author: %s", author)

        try:
            effective_results = max(1, min(num_results, 50))
            params: Dict[str, str] = {
                "response_groups": response_groups
                or "contributors,product_attrs,product_desc,product_extended_attrs,series,rating,media,relationships,customer_rights",
                "num_results": str(effective_results),
                "products_sort_by": "Relevance",
                "author": author,
                "marketplace": region,
            }

            error_handler.log_request_info(self.base_url, params, f"Search by author: {author}")

            response = self.session.get(self.base_url, params=params, timeout=30)
            if not error_handler.validate_response(response, f"Search by author: {author}"):
                return []

            error_handler.handle_api_quota(response)

            api_data = response.json()
            products = api_data.get("products", [])
            self.logger.info("Found %s books for author '%s'", len(products), author)
            return products

        except requests.exceptions.RequestException as exc:
            self.logger.error("Request error while searching author '%s': %s", author, exc)
            raise
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Unexpected error while searching author '%s': %s", author, exc)
            raise

    @error_handler.with_retry(max_retries=3, retry_delay=1.0)
    def search_by_series(self, series: str, region: str = "us", num_results: int = 25) -> List[Dict[str, Any]]:
        """Search for books in a series via keyword search."""

        self.logger.info("Searching Audible for series: %s", series)

        try:
            params = {
                "response_groups": "contributors,product_attrs,product_desc,product_extended_attrs,series,rating,media,customer_rights",
                "num_results": str(num_results),
                "products_sort_by": "Relevance",
                "keywords": f'series:"{series}"',
                "marketplace": region,
            }

            error_handler.log_request_info(self.base_url, params, f"Search by series: {series}")

            response = self.session.get(self.base_url, params=params, timeout=30)
            if not error_handler.validate_response(response, f"Search by series: {series}"):
                return []

            error_handler.handle_api_quota(response)

            api_data = response.json()
            products = api_data.get("products", [])
            self.logger.info("Found %s books for series '%s'", len(products), series)
            return products

        except requests.exceptions.RequestException as exc:
            self.logger.error("Request error while searching series '%s': %s", series, exc)
            raise
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Unexpected error while searching series '%s': %s", series, exc)
            raise

    def get_api_status(self) -> Dict[str, Any]:
        """Check whether the Audible API endpoint is reachable."""

        status: Dict[str, Any] = {
            "accessible": False,
            "base_url": self.base_url,
        }

        try:
            test_params = {
                "response_groups": "product_attrs",
                "num_results": "1",
                "keywords": "status",
                "marketplace": "us",
            }

            response = self.session.get(self.base_url, params=test_params, timeout=10)
            status["status_code"] = response.status_code

            if error_handler.validate_response(response, "API status check"):
                status["accessible"] = True

                remaining = error_handler.handle_api_quota(response)
                if remaining is not None:
                    status["quota_remaining"] = remaining

                try:
                    data = response.json()
                    status["api_version"] = data.get("version", "unknown")
                    status["products_available"] = len(data.get("products", []))
                except Exception:  # noqa: BLE001 - status gathering best effort
                    pass

            return status

        except requests.exceptions.RequestException as exc:
            self.logger.error("Request error during API status check: %s", exc)
            status["error"] = str(exc)
            return status
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Unexpected error during API status check: %s", exc)
            status["error"] = str(exc)
            return status

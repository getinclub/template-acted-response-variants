import json
from variant_cache import capture_entry, select_variant
records = [capture_entry("GET", "/help", {"Accept-Language": "fr"}, "Bonjour", vary="Accept-Language", stored_at=10, max_age=60)]
result = select_variant(records, "GET", "/help", {"Accept-Language": "en"}, 20)
print(json.dumps({"fixture": "fictional CPU replay, not production traffic", "request_language": "en", "cached_language": "fr", "expected": "MISS", "observed": "MISS" if result is None else result["body"]}, indent=2))

"""Public classification column names mapped to the existing storage fields."""
from datasets.services.iprice_upload_template_export import UPLOAD_TEMPLATE_HEADERS

FILE_TO_MODEL = {'type': 'category', 'category': 'subcategory', 'subcategory': 'subcategory_type'}
MODEL_TO_FILE = {value: key for key, value in FILE_TO_MODEL.items()}
HEADERS = tuple(MODEL_TO_FILE.get(key, key) for key in UPLOAD_TEMPLATE_HEADERS['product_classification'])

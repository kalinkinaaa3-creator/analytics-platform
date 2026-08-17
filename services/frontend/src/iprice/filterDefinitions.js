export const IPRICE_PRODUCT_FILTERS = [
  ["code_1c", "Код 1С"],
  ["nom", "Номенклатура 1С"],
  ["base_product_key", "Ключ системы"],
  ["pricing_method", "Метод расчёта"],
  ["calculation_status", "Статус расчёта"],
  ["assortment_matrix_status", "САМ"],
  ["our_offer", "Наши предложения"],
  ["nom_hier_code", "Код группировки 1С"],
  ["nom_hier", "Группировка 1С"],
  ["nom_view", "Вид номенклатуры 1С"],
  ["nom_category", "Категория номенклатуры 1С"],
  ["nom_group", "Группа номенклатуры 1С"],
  ["category", "Тип номенклатуры iPrice"],
  ["subcategory", "Категория iPrice"],
  ["subcategory_type", "Подкатегория iPrice"],
  ["color", "Цвет iPrice"],
  ["material", "Материал iPrice"],
  ["modification", "Модификация iPrice"],
];


export const IPRICE_REGION_FILTERS = [
  ...IPRICE_PRODUCT_FILTERS.slice(0, 7),
  ["sale_region", "Регион продажи"],
  ["departure", "Место производства"],
  ...IPRICE_PRODUCT_FILTERS.slice(7),
];

export const CLEAR_FILTER_SEARCH_EVENT = "iprice:clear-filter-searches";


export function clearIPriceFilterSearches() {
  window.dispatchEvent(new Event(CLEAR_FILTER_SEARCH_EVENT));
}

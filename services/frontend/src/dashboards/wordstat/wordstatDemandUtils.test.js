import test from "node:test";
import assert from "node:assert/strict";
import { defaultSeasonIds, objectNoun, sortedChanges, statusDistribution } from "./wordstatDemandUtils.js";

test("rankings match cards and exclude stable boundaries, new and missing rows", () => {
  const items = [-3, -2.01, -2, -0.1, 0, 0.1, 2, 2.01, 3].map((value) => ({
    id: String(value), absolute_change: value * 100, growth_percent: value,
    status: value > 2 ? "growth" : value < -2 ? "decline" : "stable",
  }));
  items.push({ id: "new", absolute_change: 5, growth_percent: null, status: "new" },
    { id: "missing", absolute_change: null, status: "missing" });
  assert.deepEqual(sortedChanges(items, "growth", { key: "growth_percent", direction: "desc" }).map(p => p.id), ["3", "2.01"]);
  assert.deepEqual(sortedChanges(items, "decline", { key: "absolute_change", direction: "asc" }).map(p => p.id), ["-3", "-2.01"]);
  for (const direction of ["growth", "decline"]) {
    assert.equal(sortedChanges(items, direction, { key: "growth_percent", direction: "asc" }).length, statusDistribution(items)[direction].count);
    assert.deepEqual(sortedChanges(items.filter(p => p.status === "stable"), direction, {}), []);
  }
});

test("cards count grouped items, retain missing values and use the same items as selection", () => {
  const items = [{ id:"category-a", status:"growth", current_volume:900, query_count:433 },
    { id:"category-b", status:"decline", current_volume:100, query_count:828 }];
  const result = statusDistribution(items);
  assert.equal(result.growth.count, 1);
  assert.equal(result.growth.share, 50);
  assert.equal(result.growth.volume_share, 90);
  assert.equal(statusDistribution([...items, { status:"missing", current_volume:null }]).growth.volume_share, null);
  assert.equal(statusDistribution([]).growth.share, null);
});

test("seasonality always selects at most three maxima from the eligible selection", () => {
  const items = Array.from({length:8}, (_, i) => ({id:String(i), growth_percent:i, absolute_change:i}));
  assert.deepEqual(defaultSeasonIds(items), ["7", "6", "5"]);
  assert.deepEqual(defaultSeasonIds(items.filter(p => Number(p.id) < 5)), ["4", "3", "2"]);
  assert.deepEqual(defaultSeasonIds(items.slice(0, 1)), ["0"]);
});
test("season defaults use growth rather than volume and retain the selected phrase", () => {
  const items = [1, 4, 2, 3].map((growth_percent) => ({ id: String(growth_percent), phrase: String(growth_percent), growth_percent, absolute_change: growth_percent, current_volume: 100 - growth_percent }));
  assert.deepEqual(defaultSeasonIds(items), ["4", "3", "2"]);
  assert.deepEqual(defaultSeasonIds(items, "1"), ["1", "4", "3"]);
});
test("Russian endings", () => {
  assert.deepEqual([1, 2, 5, 11, 21, 22, 114].map((n) => objectNoun(n, "feature")), ["категория", "категории", "категорий", "категорий", "категория", "категории", "категорий"]);
  assert.equal(objectNoun(3, "category"), "подкатегории");
  assert.equal(objectNoun(11, "phrase"), "запросов");
});

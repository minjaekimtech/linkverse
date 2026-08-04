import type { DemoDomain } from "./demoTypes";
export const audienceSuggestions: Record<DemoDomain, string[]> = {
  sunscreen: ["Gen Z", "beauty and skincare shoppers", "outdoor athletes", "parents"],
  soccer_equipment: ["youth soccer players", "amateur soccer players", "football fans", "parents"],
};
export const audienceKeywords: Record<string, string[]> = {
  "Gen Z": ["gen z", "teen", "trending", "학생"], "beauty and skincare shoppers": ["beauty", "skincare", "routine", "피부", "뷰티"],
  "outdoor athletes": ["outdoor", "sport", "running", "운동"], parents: ["parent", "family", "kids", "부모", "아이"],
  "youth soccer players": ["youth", "academy", "junior", "유소년"], "amateur soccer players": ["amateur", "training", "풋살", "동호회"],
  "football fans": ["soccer", "football", "match", "fan", "축구"],
};

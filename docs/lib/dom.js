// DOM helpers. Only page modules and view builders import this file.

export const $ = (id) => document.getElementById(id);

/** Create an element with an optional class and text content. */
export function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

const SVG_NS = "http://www.w3.org/2000/svg";

export function svg(tag, attributes = {}, text) {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  if (text !== undefined) element.textContent = String(text);
  return element;
}

/** Fill a <select> with one option per [value, label] pair, after an "all" option. */
export function fillSelect(select, allLabel, entries) {
  const all = node("option", "", allLabel);
  all.value = "";
  select.replaceChildren(all);
  for (const [value, label] of entries) {
    const option = node("option", "", label);
    option.value = value;
    select.append(option);
  }
}

/** Append options without clearing the existing ones (the HTML provides "All ..."). */
export function appendOptions(select, entries) {
  for (const [value, label] of entries) {
    const option = node("option", "", label);
    option.value = value;
    select.append(option);
  }
}

export function hasOption(select, value) {
  return [...select.options].some((option) => option.value === value);
}

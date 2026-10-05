/* global maplibregl */

const DATA_ROOT = "./data/";
const MINIMUM_SALE_SAMPLES = 10;

const elements = {
  stationSelect: document.querySelector("#station-minutes"),
  poolSelect: document.querySelector("#pool-minutes"),
  priceLow: document.querySelector("#price-low"),
  priceHigh: document.querySelector("#price-high"),
  status: document.querySelector("#status"),
  infoButton: document.querySelector("#info-button"),
  methodology: document.querySelector("#methodology"),
  layerToggles: document.querySelectorAll("[data-layer]"),
  poolOperatorToggles: document.querySelector("#pool-operator-toggles"),
};

const map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/liberty",
  center: [-0.11, 51.51],
  zoom: 9.6,
  minZoom: 8,
  maxZoom: 17,
  attributionControl: false,
});

map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
map.addControl(
  new maplibregl.AttributionControl({
    compact: true,
    customAttribution: [
      '<a href="https://tfl.gov.uk/info-for/open-data-users/" target="_blank">TfL</a>',
      '<a href="https://www.better.org.uk/leisure-centre/london" target="_blank">Better</a>',
      '<a href="https://www.everyoneactive.com/centre/" target="_blank">Everyone Active</a>',
      '<a href="https://www.gov.uk/government/organisations/land-registry" target="_blank">HM Land Registry</a>',
      '<a href="https://www.ordnancesurvey.co.uk/products/code-point-open" target="_blank">Contains OS data © Crown copyright 2026</a>',
    ],
  }),
  "bottom-left",
);

let allCandidates;
let sales;
let poolReach;
let stationReach;
let poolOperators = [];
let candidateFieldIndex = {};
const contextMarkers = { stations: [], pools: [] };

function setStatus(message, isError = false) {
  elements.status.textContent = message;
  elements.status.classList.toggle("error", isError);
}

function fetchJson(path) {
  return fetch(new URL(path, new URL(DATA_ROOT, document.baseURI)), {
    cache: "no-store",
  }).then((response) => {
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
  });
}

function queryValue(name) {
  return new URLSearchParams(location.search).get(name);
}

function selectedNumber(select) {
  return Number(select.value);
}

function populateMinuteSelect(select, options, selected) {
  select.replaceChildren(
    ...options.map((minutes) => {
      const option = document.createElement("option");
      option.value = String(minutes);
      option.textContent = `${minutes} minutes`;
      option.selected = minutes === selected;
      return option;
    }),
  );
}

function formatPrice(value, compact = false) {
  if (!value) return "No data";
  if (compact && value >= 1000000) {
    return `£${(value / 1000000).toFixed(value % 1000000 ? 1 : 0)}m`;
  }
  if (compact) return `£${Math.round(value / 1000)}k`;
  return `£${Math.round(value).toLocaleString("en-GB")}`;
}

function percentile(sortedValues, fraction) {
  if (!sortedValues.length) return 0;
  const index = Math.min(
    sortedValues.length - 1,
    Math.max(0, Math.round((sortedValues.length - 1) * fraction)),
  );
  return sortedValues[index];
}

function updateUrl() {
  const params = new URLSearchParams({
    stationMinutes: elements.stationSelect.value,
    poolMinutes: elements.poolSelect.value,
  });
  history.replaceState(null, "", `${location.pathname}?${params}${location.hash}`);
}

function enabledPoolOperatorIds() {
  return [...elements.poolOperatorToggles.querySelectorAll("[data-pool-operator]:checked")].map(
    (input) => input.dataset.poolOperator,
  );
}

function qualifyingPoolMinutes(point) {
  const enabled = new Set(enabledPoolOperatorIds());
  if (!enabled.size) return 99;

  let best = 99;
  for (const operator of poolOperators) {
    if (!enabled.has(operator.id)) continue;
    const minutes = point[candidateFieldIndex[operator.field]];
    if (minutes < best) best = minutes;
  }
  return best;
}

function isLayerToggleEnabled(layerId) {
  const toggle = document.querySelector(`[data-layer="${layerId}"]`);
  return toggle?.checked ?? true;
}

function refreshStationMarkerVisibility() {
  const visible = isLayerToggleEnabled("stations");
  for (const entry of contextMarkers.stations) {
    entry.marker.getElement().style.display = visible ? "" : "none";
  }
}

function refreshPoolMarkerVisibility() {
  const layerVisible = isLayerToggleEnabled("pools");
  const enabled = new Set(enabledPoolOperatorIds());
  for (const entry of contextMarkers.pools) {
    const visible = layerVisible && enabled.has(entry.operator);
    entry.marker.getElement().style.display = visible ? "" : "none";
  }
}

function updatePoolVenueFilter() {
  refreshPoolMarkerVisibility();
}

function populatePoolOperatorToggles() {
  elements.poolOperatorToggles.replaceChildren(
    ...poolOperators.map((operator) => {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.dataset.poolOperator = operator.id;
      input.checked = operator.default;
      const span = document.createElement("span");
      span.textContent = operator.label;
      label.append(input, span);
      return label;
    }),
  );
  elements.poolOperatorToggles.addEventListener("change", () => {
    updatePoolVenueFilter();
    updateCandidates();
  });
}

function updateCandidates() {
  if (!allCandidates || !sales || !map.getSource("candidates")) return;

  const stationMinutes = selectedNumber(elements.stationSelect);
  const poolMinutes = selectedNumber(elements.poolSelect);
  const enabledOperators = enabledPoolOperatorIds();
  if (!enabledOperators.length) {
    map.getSource("candidates").setData({ type: "FeatureCollection", features: [] });
    setStatus("Select at least one pool operator to show matching districts.", true);
    updateUrl();
    return;
  }

  const values = [];
  const districts = new Map();

  for (const point of allCandidates.points) {
    const postcode = point[candidateFieldIndex.postcode];
    const longitude = point[candidateFieldIndex.longitude];
    const latitude = point[candidateFieldIndex.latitude];
    const stationMin = point[candidateFieldIndex.stationMin];
    const poolMin = qualifyingPoolMinutes(point);
    if (stationMin > stationMinutes || poolMin > poolMinutes) {
      continue;
    }

    const district = postcode.split(" ")[0];
    const districtSales = sales.districts[district];
    const value = districtSales?.flatSaleMedian;
    if (!value || districtSales.saleSamples < MINIMUM_SALE_SAMPLES) {
      continue;
    }

    const poolReachEntries = poolReach?.byPostcode?.[postcode] ?? [];
    const stationReachEntries = stationReach?.byPostcode?.[postcode] ?? [];
    const aggregate = districts.get(district);
    if (aggregate) {
      aggregate.longitude += longitude;
      aggregate.latitude += latitude;
      aggregate.postcodeCount += 1;
    } else {
      districts.set(district, {
        district,
        longitude,
        latitude,
        postcodeCount: 1,
        priceValue: value,
        stations: new Map(),
        pools: new Map(),
      });
    }
    const districtAggregate = districts.get(district);
    for (const [stationIndex, minutes] of stationReachEntries) {
      if (minutes > stationMinutes) continue;
      const station = stationReach.stations[stationIndex];
      const existing = districtAggregate.stations.get(station.key);
      if (!existing || minutes < existing.minutes) {
        districtAggregate.stations.set(station.key, {
          name: station.name,
          lines: station.lines,
          minutes,
        });
      }
    }
    for (const [venueIndex, minutes] of poolReachEntries) {
      if (minutes > poolMinutes) continue;
      const venue = poolReach.venues[venueIndex];
      if (!enabledOperators.includes(venue.operator)) continue;
      const existing = districtAggregate.pools.get(venue.key);
      if (!existing || minutes < existing.minutes) {
        districtAggregate.pools.set(venue.key, {
          name: venue.name,
          operatorLabel: venue.operatorLabel,
          minutes,
        });
      }
    }
  }

  const features = Array.from(districts.values(), (district) => {
    values.push(district.priceValue);
    return {
      type: "Feature",
      id: district.district,
      properties: {
        district: district.district,
        postcodeCount: district.postcodeCount,
        priceValue: district.priceValue,
        triggeringStations: JSON.stringify(
          [...(district.stations?.values() ?? [])].sort(
            (left, right) =>
              left.minutes - right.minutes ||
              left.name.localeCompare(right.name, "en-GB"),
          ),
        ),
        triggeringPools: JSON.stringify(
          [...(district.pools?.values() ?? [])].sort(
            (left, right) =>
              left.minutes - right.minutes ||
              left.name.localeCompare(right.name, "en-GB"),
          ),
        ),
      },
      geometry: {
        type: "Point",
        coordinates: [
          district.longitude / district.postcodeCount,
          district.latitude / district.postcodeCount,
        ],
      },
    };
  });

  map.getSource("candidates").setData({
    type: "FeatureCollection",
    features,
  });

  values.sort((a, b) => a - b);
  const low = percentile(values, 0.1);
  const middle = percentile(values, 0.5);
  let high = percentile(values, 0.9);
  if (high <= low) high = low + 1;

  map.setPaintProperty("candidate-points", "circle-color", [
    "interpolate",
    ["linear"],
    ["get", "priceValue"],
    low,
    "#2a9d8f",
    middle,
    "#e9c46a",
    high,
    "#e76f51",
  ]);
  elements.priceLow.textContent = formatPrice(low, true);
  elements.priceHigh.textContent = formatPrice(high, true);

  const postcodeCount = features.reduce(
    (total, feature) => total + feature.properties.postcodeCount,
    0,
  );
  setStatus(
    `${features.length.toLocaleString("en-GB")} districts from ${postcodeCount.toLocaleString("en-GB")} qualifying postcodes · ${sales.meta.salePeriod}`,
  );
  updateUrl();
}

function addCandidateLayers() {
  map.addLayer({
    id: "candidate-points",
    type: "circle",
    source: "candidates",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 6, 13, 9],
      "circle-color": "#2a9d8f",
      "circle-opacity": 0.86,
      "circle-stroke-color": "#fff",
      "circle-stroke-width": 1.5,
    },
  });

  map.on("click", "candidate-points", (event) => {
    const feature = event.features?.[0];
    if (feature) showCandidatePopup(feature);
  });

  map.on("mouseenter", "candidate-points", () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "candidate-points", () => {
    map.getCanvas().style.cursor = "";
  });
}

function createEmojiMarker(emoji, label, coordinates, onSelect) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "emoji-marker";
  button.textContent = emoji;
  button.setAttribute("aria-label", label);
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    onSelect();
  });
  const marker = new maplibregl.Marker({ element: button, anchor: "center" })
    .setLngLat(coordinates)
    .addTo(map);
  return marker;
}

function addContextMarkers(stations, venues) {
  for (const feature of stations.features) {
    const coordinates = feature.geometry.coordinates;
    const properties = feature.properties;
    const marker = createEmojiMarker(
      "🚇",
      properties.name,
      coordinates,
      () => showContextPopup("station", properties, coordinates),
    );
    contextMarkers.stations.push({ marker });
  }

  for (const feature of venues.features) {
    const coordinates = feature.geometry.coordinates;
    const properties = feature.properties;
    const marker = createEmojiMarker(
      "🏊",
      properties.name,
      coordinates,
      () => showContextPopup("pool", properties, coordinates),
    );
    contextMarkers.pools.push({
      marker,
      operator: properties.operator,
    });
  }
}

function addLayerToggleListeners() {
  for (const toggle of elements.layerToggles) {
    toggle.addEventListener("change", () => {
      const layerId = toggle.dataset.layer;
      if (layerId === "candidate-points") {
        map.setLayoutProperty(layerId, "visibility", toggle.checked ? "visible" : "none");
        return;
      }
      if (layerId === "stations") {
        refreshStationMarkerVisibility();
        return;
      }
      if (layerId === "pools") {
        refreshPoolMarkerVisibility();
      }
    });
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatReachSection(title, items, formatMeta) {
  if (!items.length) {
    return "";
  }
  const list = items
    .map(
      (item) =>
        `<li>${escapeHtml(item.name)} <span class="popup-reach-meta">(${formatMeta(
          item,
        )})</span></li>`,
    )
    .join("");
  return `<br><br><b>${escapeHtml(title)}</b><ul class="popup-reach-list">${list}</ul>`;
}

function parseReachProperty(properties, key) {
  try {
    return JSON.parse(properties[key] || "[]");
  } catch {
    return [];
  }
}

function formatTriggeringStations(properties, stationMinutes) {
  return formatReachSection(
    `Night Tube within ${stationMinutes} min walk:`,
    parseReachProperty(properties, "triggeringStations"),
    (station) => `${escapeHtml(station.lines)}, ≤${station.minutes} min`,
  );
}

function formatTriggeringPools(properties, poolMinutes) {
  return formatReachSection(
    `Pools within ${poolMinutes} min walk:`,
    parseReachProperty(properties, "triggeringPools"),
    (pool) => `${escapeHtml(pool.operatorLabel)}, ≤${pool.minutes} min`,
  );
}

function showCandidatePopup(feature) {
  const properties = feature.properties;
  const districtSales = sales.districts[properties.district] ?? {};
  const saleRange =
    districtSales.flatSaleLower && districtSales.flatSaleUpper
      ? `${formatPrice(districtSales.flatSaleLower)}–${formatPrice(
          districtSales.flatSaleUpper,
        )}`
      : "No range";
  const stationMinutes = selectedNumber(elements.stationSelect);
  const poolMinutes = selectedNumber(elements.poolSelect);

  new maplibregl.Popup({ offset: 8 })
    .setLngLat(feature.geometry.coordinates)
    .setHTML(`
      <strong>${escapeHtml(properties.district)}</strong>
      ${properties.postcodeCount.toLocaleString("en-GB")} postcode locations match the selected walking limits.<br>
      <br><b>${escapeHtml(properties.district)} median flat sale:</b>
      ${formatPrice(districtSales.flatSaleMedian)}<br>
      <small>${saleRange}; ${districtSales.saleSamples ?? 0} sales</small>
      ${formatTriggeringStations(properties, stationMinutes)}
      ${formatTriggeringPools(properties, poolMinutes)}
    `)
    .addTo(map);
}

function showContextPopup(kind, properties, coordinates) {
  const detail =
    kind === "station"
      ? `<br>Night service: ${escapeHtml(properties.lines)}`
      : `<br>${escapeHtml(properties.operatorLabel || "Pool")} · ${escapeHtml(
          properties.address || "Gym with pool",
        )}`;
  new maplibregl.Popup({ offset: 12 })
    .setLngLat(coordinates)
    .setHTML(`<strong>${escapeHtml(properties.name)}</strong>${detail}`)
    .addTo(map);
}

async function initialise() {
  try {
    const manifest = await fetchJson("manifest.json");
    poolOperators = manifest.poolOperators ?? [];
    const [candidateData, saleData, stations, venues, poolReachData, stationReachData] =
      await Promise.all([
        fetchJson(manifest.files.candidates),
        fetchJson(manifest.files.sales),
        fetchJson(manifest.files.stations),
        fetchJson(manifest.files.venues),
        fetchJson(manifest.files.poolReach ?? "postcode-pool-reach.json"),
        fetchJson(manifest.files.stationReach ?? "postcode-station-reach.json"),
      ]);
    allCandidates = candidateData;
    sales = saleData;
    poolReach = poolReachData;
    stationReach = stationReachData;
    candidateFieldIndex = Object.fromEntries(
      allCandidates.fields.map((name, index) => [name, index]),
    );
    populatePoolOperatorToggles();

    const options = manifest.options;
    const requestedStation = Number(queryValue("stationMinutes"));
    const requestedPool = Number(queryValue("poolMinutes"));
    populateMinuteSelect(
      elements.stationSelect,
      options,
      options.includes(requestedStation)
        ? requestedStation
        : manifest.defaults.station,
    );
    populateMinuteSelect(
      elements.poolSelect,
      options,
      options.includes(requestedPool) ? requestedPool : manifest.defaults.pool,
    );

    map.addSource("candidates", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    addContextMarkers(stations, venues);
    addCandidateLayers();
    addLayerToggleListeners();
    refreshStationMarkerVisibility();
    updatePoolVenueFilter();
    updateCandidates();

    elements.stationSelect.addEventListener("change", updateCandidates);
    elements.poolSelect.addEventListener("change", updateCandidates);
  } catch (error) {
    console.error(error);
    setStatus("Could not load the generated map data.", true);
  }
}

elements.infoButton.addEventListener("click", () => {
  const willOpen = elements.methodology.hidden;
  elements.methodology.hidden = !willOpen;
  elements.infoButton.setAttribute("aria-expanded", String(willOpen));
});

map.on("load", initialise);

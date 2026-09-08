/* Build-time adapter for the pinned Azgaar release. Never shipped in the viewer. */
async ({count, seed}) => {
  // The original editor randomizes unlocked settings. This build supplies all
  // relevant settings explicitly and generates a fresh world in an empty profile.
  randomizeOptions = () => {};
  mapWidthInput.value = 2400;
  mapHeightInput.value = 1550;
  pointsInput.dataset.cells = 60000;
  templateInput.add(new Option("Continents", "continents"));
  templateInput.value = "continents";
  statesNumber.value = count;
  sizeVariety.value = 7;
  growthRate.value = 3;
  culturesInput.value = culturesOutput.value = 24;
  manorsInput.value = 0;
  provincesRatio.value = 0;
  religionsNumber.value = 0;
  precInput.value = precOutput.value = 110;
  options.temperatureEquator = 26;
  options.temperatureNorthPole = -15;
  options.temperatureSouthPole = -5;
  // Fictional wars, armies and trade routes are irrelevant to our artifact.
  States.generateCampaigns = () => {};
  States.generateDiplomacy = () => {};
  Military.generate = () => {};
  Markers.generate = () => {};
  Zones.generate = () => {};
  await generate({seed: String(seed)});
  const live = pack.states.filter(s => s.i && !s.removed);
  if (live.length !== count) throw new Error(`Azgaar made ${live.length} countries, expected ${count}`);
  const isolines = getIsolines(pack, i => pack.cells.state[i], {fill:true});
  drawRivers();
  const countries = live.map(s => ({
    id:s.i, area:s.area, x:s.pole[0], y:s.pole[1],
    path:isolines[s.i]?.fill || ""
  }));
  if (countries.some(s => !s.path)) throw new Error("A country has no outline");
  // Select a bounded set of terrain motifs, separated spatially. We render
  // our own Scalaland-style symbols, rather than thousands of editor icons.
  const occupied = new Set();
  const decor = [];
  for (const i of pack.cells.i) {
    const h = pack.cells.h[i];
    if (h < 20 || pack.cells.r[i]) continue;
    const [x,y] = pack.cells.p[i];
    const kind = h >= 58 ? "mountain" : [6,7,8,9].includes(pack.cells.biome[i]) ? "forest" : null;
    const key = `${Math.floor(x/24)},${Math.floor(y/24)}`;
    if (!kind || occupied.has(key)) continue;
    occupied.add(key);
    decor.push([kind, Math.round(x), Math.round(y), h >= 70 ? 1.3 : 1]);
  }
  return {
    width:graphWidth, height:graphHeight, seed,
    countries,
    land:pack.features.filter(f => f?.land).map(getFeaturePath),
    lakes:pack.features.filter(f => f?.type === "lake").map(getFeaturePath),
    rivers:Array.from(document.querySelectorAll("#rivers path"), p => p.getAttribute("d")),
    decor,
    cells:pack.cells.i.length
  };
}

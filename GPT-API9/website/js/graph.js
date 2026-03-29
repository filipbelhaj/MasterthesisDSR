(function (global) {
  "use strict";

  const DEFAULT_LAYOUT = {
    name: "cose",
    animate: false,
    fit: true,
    randomize: false,
    padding: 24,
    nodeRepulsion: 220000,
    idealEdgeLength: 110,
    edgeElasticity: 90,
    componentSpacing: 80,
    gravity: 1.0,
    numIter: 260,
    initialTemp: 120,
    coolingFactor: 0.96,
    minTemp: 1.0,
  };

  const PLACEHOLDER_ENTITY_RE = /^NEW:entity_\d+$/;

  function isUrl(x) {
    return typeof x === "string" && (x.startsWith("http://") || x.startsWith("https://"));
  }

  function isEntityRef(x) {
    return typeof x === "string" && (isUrl(x) || PLACEHOLDER_ENTITY_RE.test(x));
  }

  function nodeIdFromValue(v) {
    return isEntityRef(v) ? v : "lit:" + String(v);
  }

  function labelForNode(id, hint) {
    if (hint && String(hint).trim()) return String(hint);
    if (id.startsWith("lit:")) return id.slice(4);
    try {
      const u = new URL(id);
      return u.pathname.split("/").filter(Boolean).pop() || id;
    } catch {
      return id;
    }
  }

  function statementKey(s) {
    const qp = s.qualifierProperty || "";
    const qv = s.qualifierValue || "";
    return `${s.item || ""}|${s.property || ""}|${String(s.value ?? "")}|${qp}|${String(qv ?? "")}`;
  }

  function hashString(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function seededPoint(id, spread = 900) {
    const xSeed = hashString(String(id));
    const ySeed = hashString(`${id}::y`);
    return {
      x: (xSeed % spread) - spread / 2,
      y: (ySeed % spread) - spread / 2,
    };
  }

  function buildElements(oldArr, newArr) {
    const prevSet = new Set(oldArr.map(statementKey));

    const labelById = new Map();
    for (const s of [...oldArr, ...newArr]) {
      if (s && s.item && s.itemLabel) labelById.set(s.item, s.itemLabel);
      if (!s) continue;
      if (typeof s.value !== "undefined" && s.valueLabel) labelById.set(nodeIdFromValue(s.value), s.valueLabel);
      if (typeof s.qualifierValue !== "undefined" && s.qualifierValueLabel) labelById.set(nodeIdFromValue(s.qualifierValue), s.qualifierValueLabel);
    }

    const oldNodeSet = new Set();
    for (const s of oldArr) {
      if (!s || !s.item || typeof s.value === "undefined") continue;
      oldNodeSet.add(s.item);
      oldNodeSet.add(nodeIdFromValue(s.value));
      if (s.qualifierProperty && typeof s.qualifierValue !== "undefined") {
        oldNodeSet.add(nodeIdFromValue(s.qualifierValue));
      }
    }

    const nodeMap = new Map();
    const edgeMap = new Map();

    const upsertNode = (id, label, status, preferLabel = false) => {
      const ex = nodeMap.get(id);
      if (!ex) return nodeMap.set(id, { data: { id, label, status }, position: seededPoint(id) });
      if (ex.data.status !== "new" && status === "new") ex.data.status = "new";
      if (label && (preferLabel || !ex.data.label || ex.data.label.length < label.length)) {
        ex.data.label = label;
      }
    };

    const upsertEdge = (id, source, target, label, status) => {
      const ex = edgeMap.get(id);
      if (!ex) return edgeMap.set(id, { data: { id, source, target, label, status } });
      if (ex.data.status !== "new" && status === "new") ex.data.status = "new";
    };

    for (const s of newArr) {
      if (!s || !s.item || !s.property || typeof s.value === "undefined") continue;

      const edgeStatus = prevSet.has(statementKey(s)) ? "existing" : "new";
      const itemId = s.item;
      const valueId = nodeIdFromValue(s.value);

      const itemHint = labelById.get(itemId);
      upsertNode(
        itemId,
        labelForNode(itemId, itemHint),
        oldNodeSet.has(itemId) ? "existing" : "new",
        !!itemHint
      );

      const valueHint = labelById.get(valueId) || null;
      upsertNode(
        valueId,
        labelForNode(valueId, valueHint),
        oldNodeSet.has(valueId) ? "existing" : "new",
        !!valueHint
      );

      upsertEdge(`${itemId}|${s.property}|${valueId}`, itemId, valueId, s.propertyLabel || labelForNode(s.property), edgeStatus);

      if (s.qualifierProperty && typeof s.qualifierValue !== "undefined") {
        const qvId = nodeIdFromValue(s.qualifierValue);
        const qualifierHint = labelById.get(qvId);
        upsertNode(
          qvId,
          labelForNode(qvId, qualifierHint),
          oldNodeSet.has(qvId) ? "existing" : "new",
          !!qualifierHint
        );
        upsertEdge(`${valueId}|${s.qualifierProperty}|${qvId}`, valueId, qvId, s.qualifierPropertyLabel || labelForNode(s.qualifierProperty), edgeStatus);
      }
    }

    return [...nodeMap.values(), ...edgeMap.values()];
  }

  function readColorVar(name, fallback) {
    const color = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return color || fallback;
  }

  function buildStyle(includeHiddenClass) {
    const NEW_COLOR = readColorVar("--newColor", "#ff3b30");
    const OLD_NODE_COLOR = readColorVar("--oldNodeColor", "#1f8b4c");
    const OLD_EDGE_COLOR = readColorVar("--oldEdgeColor", "#4fb36d");

    const styles = [
      { selector: "node", style: {
        label: "data(label)",
        "font-size": 10,
        color: "#1f2937",
        "font-weight": 600,
        "text-wrap": "wrap",
        "text-max-width": 140,
        "text-background-color": "#fff",
        "text-background-opacity": 0.92,
        "text-background-shape": "roundrectangle",
        "text-background-padding": "2px",
        "text-border-color": "#d7e2ee",
        "text-border-width": 1,
        "background-color": OLD_NODE_COLOR,
        "border-width": 2,
        "border-color": "#143a61",
        width: 38,
        height: 38,
      }},
      { selector: 'node[status="new"]', style: { "background-color": NEW_COLOR, "border-color": "#8f360d", width: 42, height: 42 }},
      { selector: "edge", style: {
        "curve-style": "bezier",
        "loop-direction": "-45deg",
        "loop-sweep": "90deg",
        "line-color": OLD_EDGE_COLOR,
        "target-arrow-shape": "triangle",
        "target-arrow-color": OLD_EDGE_COLOR,
        "target-arrow-fill": "filled",
        "arrow-scale": 1.15,
        width: 2.6,
        label: "data(label)",
        "font-size": 10,
        "font-weight": 600,
        color: "#1f2937",
        "text-wrap": "wrap",
        "text-max-width": 160,
        "text-background-color": "#fff",
        "text-background-opacity": 0.92,
        "text-background-shape": "roundrectangle",
        "text-background-padding": "2px",
        "text-border-color": "#d7e2ee",
        "text-border-width": 1,
        "text-rotation": "autorotate",
      }},
      { selector: 'edge[status="new"]', style: {
        "line-color": NEW_COLOR,
        "target-arrow-color": NEW_COLOR,
        "arrow-scale": 1.35,
        width: 3.8,
      }},
    ];

    if (includeHiddenClass) styles.push({ selector: ".cy-hidden", style: { display: "none" } });
    return styles;
  }

  function previousNodePositions(existingCy) {
    const positions = new Map();
    if (!existingCy) {
      return positions;
    }
    existingCy.nodes().forEach((node) => {
      positions.set(node.id(), { ...node.position() });
    });
    return positions;
  }

  function applyPreviousPositions(elements, positions) {
    if (!(positions instanceof Map) || positions.size === 0) {
      return elements;
    }
    return elements.map((element) => {
      const id = element?.data?.id;
      if (!id || !positions.has(id)) {
        return element;
      }
      return {
        ...element,
        position: positions.get(id),
      };
    });
  }

  function renderGraph(existingCy, container, oldArr, newArr, includeHiddenClass, options = {}) {
    if (!container || typeof global.cytoscape === "undefined") return null;
    const preservePositions = !!options.preservePositions;
    const positions = preservePositions ? previousNodePositions(existingCy) : new Map();
    const elements = applyPreviousPositions(buildElements(oldArr || [], newArr || []), positions);
    if (existingCy) existingCy.destroy();

    return global.cytoscape({
      container,
      elements,
      style: buildStyle(!!includeHiddenClass),
      layout: preservePositions
        ? { name: "preset", fit: true, padding: 24 }
        : DEFAULT_LAYOUT,
      wheelSensitivity: 0.2,
    });
  }

  function relayout(cy) {
    if (!cy) return;
    const layout = cy.layout({ ...DEFAULT_LAYOUT, randomize: true, fit: true });
    layout.run();
    return layout;
  }

  global.TriExtractGraph = {
    renderGraph,
    relayout,
  };
})(window);

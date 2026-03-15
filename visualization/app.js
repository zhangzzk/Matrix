const params = new URLSearchParams(window.location.search);
const DEFAULT_SESSION_PATH = params.get("session") || "../.dreamdive/simulation_session.json";
const PAGE_MODE = document.body.dataset.view || "story";

const EVENT_COLORS = {
  goal_collision: "#8c2f2a",
  spotlight: "#8c2f2a",
  foreground: "#d07a3e",
  background: "#8a8f99",
  solo: "#2f5d86",
  world: "#4f7a51",
  scheduled: "#b89550",
};

const LOCATION_COLORS = [
  "#274c77",
  "#8d6e63",
  "#4f6d4a",
  "#8f3f2b",
  "#5f577a",
  "#537188",
  "#976c4b",
  "#596f66",
];

const STORAGE_LAYER_CATALOG = [
  {
    id: "artifacts",
    label: "Ingestion Artifacts",
    mode: "source-derived",
    description: "Source parsing produces JSON artifacts before simulation starts. They hold extracted structure, chapter slices, meta notes, and entities.",
    examples: ["structural_scan", "chapters/*", "meta_layer", "entities"],
  },
  {
    id: "session",
    label: "Session Checkpoint",
    mode: "primary",
    description: "The main persisted object is one session JSON with current agent snapshots, current arc state, pending queues, and the append-only history.",
  },
  {
    id: "append",
    label: "Append-Only History",
    mode: "primary",
    description: "Temporal logs capture what changed over story time. Replay reads these families back to reconstruct prior state at any cursor.",
  },
  {
    id: "postgres",
    label: "Optional SQL Mirror",
    mode: "secondary",
    description: "PostgreSQL mirrors the history into queryable tables and keeps a JSONB checkpoint row, but it is not the default persistence path.",
  },
];

const SESSION_FIELD_META = {
  source_path: {
    role: "Source pointer",
    description: "Which manuscript or source file this session came from.",
  },
  current_tick_label: {
    role: "Cursor label",
    description: "Human-readable label for the latest simulated checkpoint.",
  },
  current_timeline_index: {
    role: "Narrative time",
    description: "Sortable story-time index used for replay and scheduling.",
  },
  arc_state: {
    role: "World summary",
    description: "Latest aggregate world / narrative arc state at the current cursor.",
  },
  agents: {
    role: "Live snapshots",
    description: "Current denormalized runtime state for every tracked agent.",
  },
  pending_world_events: {
    role: "Future queue",
    description: "World events still waiting to trigger at future timeline indices.",
  },
  pending_background_jobs: {
    role: "Async queue",
    description: "Maintenance and background work items carried with the session.",
  },
  append_only_log: {
    role: "History store",
    description: "All temporal log buckets that make replay and branching possible.",
  },
  metadata: {
    role: "Metadata",
    description: "Story context, tick metadata, ingestion notes, and simulation extras.",
  },
};

const AGENT_STATIC_FIELDS = [
  "identity.name",
  "identity.background",
  "identity.core_traits",
  "identity.values",
  "identity.fears",
  "identity.desires",
  "identity.domain_attributes",
];

const AGENT_DYNAMIC_FIELDS = [
  "current_state",
  "goals",
  "working_memory",
  "relationships",
  "inferred_state",
  "needs_reprojection",
  "voice_samples",
  "world_entities",
];

const LOG_FAMILY_META = [
  {
    key: "state_changes",
    label: "state_changes",
    kind: "temporal log",
    description: "Per-agent dimension writes. This is the main explicit time-series store for character state replay.",
    fields: ["character_id", "dimension", "from_value", "to_value", "replay_key"],
  },
  {
    key: "goal_stacks",
    label: "goal_stacks",
    kind: "snapshot log",
    description: "Whole goal-stack snapshots over time rather than per-goal diffs.",
    fields: ["character_id", "goals", "replay_key"],
  },
  {
    key: "relationships",
    label: "relationships",
    kind: "temporal edges",
    description: "Directional trust and sentiment updates between agents across time.",
    fields: ["from_character_id", "to_character_id", "trust_value", "sentiment_shift", "replay_key"],
  },
  {
    key: "episodic_memories",
    label: "episodic_memories",
    kind: "memory log",
    description: "Append-only event memories with salience and retrieval metadata.",
    fields: ["character_id", "memory_text", "salience", "embedding", "replay_key"],
  },
  {
    key: "entity_representations",
    label: "entity_representations",
    kind: "subjective views",
    description: "Agent-specific views of entities. The SQL mirror treats this as latest-only rather than fully temporal.",
    fields: ["entity_id", "agent_id", "representation_text"],
  },
  {
    key: "world_snapshots",
    label: "world_snapshots",
    kind: "world checkpoints",
    description: "Aggregate narrative arc snapshots, including unresolved threads and next tick size.",
    fields: ["narrative_arc", "agent_locations", "next_tick_size_minutes", "replay_key"],
  },
  {
    key: "event_log",
    label: "event_log",
    kind: "committed scenes",
    description: "Events that have already happened in the simulation branch.",
    fields: ["event_id", "timeline_index", "participants", "description", "salience"],
  },
  {
    key: "scheduled_world_events",
    label: "scheduled_world_events",
    kind: "future queue",
    description: "Future world beats waiting to become committed events.",
    fields: ["event_id", "trigger_timeline_index", "affected_agents", "seed_type"],
  },
  {
    key: "maintenance_log",
    label: "maintenance_log",
    kind: "ops trace",
    description: "Maintenance records and system-internal housekeeping entries.",
    fields: ["kind", "message", "timeline_index"],
  },
  {
    key: "llm_issues",
    label: "llm_issues",
    kind: "diagnostics",
    description: "Structured-output failures, empty responses, and schema/runtime issues.",
    fields: ["timeline_index", "phase", "prompt_name", "schema_name", "error_type"],
  },
];

const SQL_TABLE_CATALOG = [
  {
    id: "characters",
    group: "Identity scaffold",
    kind: "static scaffold",
    description: "Static character scaffold table defined in SQL, but not the active source of truth in the default session-first flow.",
    fields: ["character_id", "name", "background", "core_traits", "values"],
    note: "Runtime reads current agent snapshots from the session checkpoint instead.",
  },
  {
    id: "state_change_log",
    group: "Temporal agent logs",
    kind: "temporal log",
    description: "Append-only per-agent dimension changes keyed by replay metadata.",
    fields: ["character_id", "dimension", "from_value", "to_value", "replay_key"],
  },
  {
    id: "goal_stack",
    group: "Temporal agent logs",
    kind: "snapshot log",
    description: "Time-versioned goal stack snapshots per character.",
    fields: ["character_id", "goals", "replay_key"],
  },
  {
    id: "relationship_log",
    group: "Relation logs",
    kind: "temporal edges",
    description: "Directional relationship updates between agents over time.",
    fields: ["from_character_id", "to_character_id", "trust_value", "trust_delta", "sentiment_shift", "replay_key"],
  },
  {
    id: "episodic_memory",
    group: "Temporal agent logs",
    kind: "memory log",
    description: "Append-only memory rows with salience and pgvector embeddings for retrieval.",
    fields: ["character_id", "memory_text", "salience", "embedding", "replay_key"],
  },
  {
    id: "event_log",
    group: "World logs",
    kind: "committed events",
    description: "World and scene events that have already been resolved.",
    fields: ["event_id", "timeline_index", "participants", "description", "salience"],
  },
  {
    id: "world_snapshot",
    group: "World logs",
    kind: "aggregate snapshot",
    description: "One world-level narrative snapshot per replay point when available.",
    fields: ["replay_key", "narrative_arc", "agent_locations", "unresolved_threads"],
    note: "Worlds are aggregated here; there is no first-class worlds table in the current design.",
  },
  {
    id: "entity",
    group: "Perception and retrieval",
    kind: "entity store",
    description: "Objective entity facts and embeddings for shared world knowledge.",
    fields: ["entity_id", "canonical_name", "facts", "embedding"],
    note: "This is part of the optional SQL mirror, not the live session payload.",
  },
  {
    id: "entity_representation",
    group: "Perception and retrieval",
    kind: "latest-only",
    description: "Subjective agent-to-entity view. Stored as a latest row per entity-agent pair, not a full temporal log.",
    fields: ["entity_id", "agent_id", "representation_text", "updated_at"],
  },
  {
    id: "simulation_session",
    group: "Checkpoint",
    kind: "JSONB checkpoint",
    description: "Stores the whole session checkpoint payload as a single SQL row when the Postgres backend is enabled.",
    fields: ["session_id", "session_payload", "updated_at"],
    note: "Only this table is session-scoped in the current SQL path.",
  },
];

const state = {
  model: null,
  tick: 0,
  mode: "external",
  visibleCharacterIds: new Set(),
  panel: null,
  isPlaying: false,
  playSpeed: 1,
  playbackHandle: null,
  showDiagnostics: false,
};

const root = document.getElementById("app");

initialize();

async function initialize() {
  try {
    const { session, rawBytes } = await fetchSession(DEFAULT_SESSION_PATH);
    state.model = buildModel(session, DEFAULT_SESSION_PATH, { rawBytes });
    state.tick = state.model.currentTick;
    state.visibleCharacterIds = new Set(state.model.characters.map((character) => character.id));
    installTestingHooks();
    render();
    window.addEventListener("resize", debounce(render, 120));
  } catch (error) {
    renderError(error);
  }
}

async function fetchSession(sessionPath) {
  const response = await fetch(sessionPath, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Unable to load session data from ${sessionPath}. HTTP ${response.status}.`);
  }
  const text = await response.text();
  return {
    session: JSON.parse(text),
    rawBytes: new TextEncoder().encode(text).length,
  };
}

function buildModel(session, sessionPath, options = {}) {
  const appendOnly = {
    state_changes: [],
    goal_stacks: [],
    relationships: [],
    episodic_memories: [],
    world_snapshots: [],
    event_log: [],
    scheduled_world_events: [],
    maintenance_log: [],
    entity_representations: [],
    ...(session.append_only_log || {}),
  };
  const characters = Object.entries(session.agents || {})
    .map(([id, agent]) => normalizeCharacter(id, agent))
    .sort((left, right) => left.name.localeCompare(right.name));
  const characterById = Object.fromEntries(characters.map((character) => [character.id, character]));
  const refMap = new Map();
  for (const character of characters) {
    refMap.set(normalizeRef(character.id), character.id);
    refMap.set(normalizeRef(character.name), character.id);
  }
  const stateChanges = appendOnly.state_changes
    .map((entry) => ({
      ...entry,
      replay_key: normalizeReplayKey(entry.replay_key),
    }))
    .sort(compareReplayItems);
  const goalStacks = appendOnly.goal_stacks
    .map((entry) => ({
      ...entry,
      replay_key: normalizeReplayKey(entry.replay_key),
      goals: Array.isArray(entry.goals) ? entry.goals : [],
    }))
    .sort(compareReplayItems);
  const relationships = appendOnly.relationships
    .map((entry) => ({
      ...entry,
      replay_key: normalizeReplayKey(entry.replay_key),
    }))
    .sort(compareReplayItems);
  const memories = appendOnly.episodic_memories
    .map((entry) => ({
      ...entry,
      replay_key: normalizeReplayKey(entry.replay_key),
    }))
    .sort(compareReplayItems);
  const snapshots = appendOnly.world_snapshots
    .map((entry) => ({
      ...entry,
      replay_key: normalizeReplayKey(entry.replay_key),
      next_tick_size_minutes: Number(entry.next_tick_size_minutes || 0),
    }))
    .sort(compareReplayItems);
  const llmIssues = (appendOnly.llm_issues || [])
    .map((entry, index) => ({
      issue_id: String(entry?.issue_id || `llm_issue_${index + 1}`),
      timeline_index: Number(entry?.timeline_index || 0),
      tick_label: String(entry?.tick_label || "snapshot"),
      phase: String(entry?.phase || "tick"),
      prompt_name: String(entry?.prompt_name || "prompt"),
      profile_name: String(entry?.profile_name || ""),
      schema_name: String(entry?.schema_name || ""),
      stage: String(entry?.stage || ""),
      error_type: String(entry?.error_type || ""),
      error_message: String(entry?.error_message || ""),
      response_was_empty: Boolean(entry?.response_was_empty),
      response_preview: String(entry?.response_preview || ""),
      character_id: String(entry?.character_id || ""),
      seed_id: String(entry?.seed_id || ""),
      chapter_id: String(entry?.chapter_id || ""),
      attempt_index: Number(entry?.attempt_index || 0),
    }))
    .sort((left, right) => left.timeline_index - right.timeline_index);
  const tickDurationByTick = Object.create(null);
  for (const snapshot of snapshots) {
    const tick = Number(snapshot.replay_key.timeline_index || 0);
    const minutes = Number(snapshot.next_tick_size_minutes || 0);
    if (minutes > 0) {
      tickDurationByTick[tick] = minutes;
    }
  }
  const currentTick = Number(session.current_timeline_index || 0);
  const latestTickMinutes = Number(session.metadata?.last_tick_minutes || 0);
  if (latestTickMinutes > 0 && !tickDurationByTick[currentTick]) {
    tickDurationByTick[currentTick] = latestTickMinutes;
  }
  const loggedEvents = appendOnly.event_log
    .map((event) => ({
      ...event,
      event_kind: "logged",
      timeline_index: Number(event.timeline_index || 0),
      participants: normalizeParticipants(event.participants),
      salience: Number(event.salience || 0),
      seed_type: (event.seed_type || "").toLowerCase(),
    }))
    .sort((left, right) => left.timeline_index - right.timeline_index);
  const scheduledEvents = (session.pending_world_events || appendOnly.scheduled_world_events || [])
    .map((event) => ({
      ...event,
      event_kind: "scheduled",
      timeline_index: Number(event.trigger_timeline_index || 0),
      participants: normalizeParticipants(event.affected_agents),
      salience: 0,
      seed_type: "scheduled",
      outcome_summary: "",
      resolution_mode: "scheduled",
    }))
    .sort((left, right) => left.timeline_index - right.timeline_index);
  const timePoints = collectTimePoints({
    currentTick: Number(session.current_timeline_index || 0),
    stateChanges,
    goalStacks,
    relationships,
    memories,
    snapshots,
    loggedEvents,
    scheduledEvents,
  });
  const locationPalette = buildLocationPalette(stateChanges, characters);
  const initialArc = session.metadata?.initial_arc_state || session.arc_state || {};
  const storageAtlas = buildStorageAtlas({
    session,
    sessionPath,
    rawBytes: Number(options.rawBytes || 0),
    appendOnly,
    characters,
    stateChanges,
    goalStacks,
    relationships,
    memories,
    snapshots,
    llmIssues,
    loggedEvents,
    scheduledEvents,
    pendingWorldEventCount: Array.isArray(session.pending_world_events) ? session.pending_world_events.length : 0,
    backgroundJobCount: Array.isArray(session.pending_background_jobs) ? session.pending_background_jobs.length : 0,
  });
  return {
    session,
    sessionPath,
    title: humanizeSlug(session.metadata?.story_context || basenameStem(session.source_path) || "Novel Simulation"),
    sourcePath: session.source_path || "",
    metadata: session.metadata || {},
    currentTick,
    currentTickLabel: session.current_tick_label || "snapshot",
    characters,
    characterById,
    refMap,
    stateChanges,
    goalStacks,
    relationships,
    memories,
    snapshots,
    llmIssues,
    tickDurationByTick,
    loggedEvents,
    scheduledEvents,
    timelineItems: [...loggedEvents, ...scheduledEvents].sort((left, right) => left.timeline_index - right.timeline_index),
    locationPalette,
    timePoints,
    minTick: Math.min(...timePoints),
    maxTick: Math.max(...timePoints),
    initialArc,
    storageAtlas,
  };
}

function normalizeCharacter(id, agent) {
  const snapshot = agent?.snapshot || {};
  const identity = snapshot.identity || {};
  const normalizedIdentity = {
    ...identity,
    core_traits: normalizeTextList(identity.core_traits),
    values: normalizeTextList(identity.values),
    fears: normalizeTextList(identity.fears),
    desires: normalizeTextList(identity.desires),
    universal_dimensions: ensureRecord(identity.universal_dimensions),
    prominent_dimensions: ensureRecord(identity.prominent_dimensions),
    domain_attributes: ensureRecord(identity.domain_attributes),
  };
  return {
    id,
    name: identity.name || humanizeSlug(id),
    snapshot: snapshot,
    identity: normalizedIdentity,
    needsReprojection: Boolean(agent?.needs_reprojection),
    voiceSamples: Array.isArray(agent?.voice_samples) ? agent.voice_samples : [],
    worldEntities: Array.isArray(agent?.world_entities) ? agent.world_entities : [],
  };
}

function normalizeReplayKey(replayKey) {
  return {
    tick: replayKey?.tick || "snapshot",
    timeline_index: Number(replayKey?.timeline_index || 0),
    event_sequence: Number(replayKey?.event_sequence || 0),
  };
}

function compareReplayItems(left, right) {
  return (
    left.replay_key.timeline_index - right.replay_key.timeline_index ||
    left.replay_key.event_sequence - right.replay_key.event_sequence
  );
}

function collectTimePoints(input) {
  const points = new Set([0, Number(input.currentTick || 0)]);
  for (const item of [
    ...input.stateChanges,
    ...input.goalStacks,
    ...input.relationships,
    ...input.memories,
    ...input.snapshots,
  ]) {
    points.add(Number(item.replay_key.timeline_index || 0));
  }
  for (const event of [...input.loggedEvents, ...input.scheduledEvents]) {
    points.add(Number(event.timeline_index || 0));
  }
  return [...points].sort((left, right) => left - right);
}

function buildLocationPalette(stateChanges, characters) {
  const locations = [];
  for (const entry of stateChanges) {
    if (entry.dimension === "location" && typeof entry.to_value === "string" && entry.to_value.trim()) {
      locations.push(entry.to_value.trim());
    }
  }
  for (const character of characters) {
    const location = character.snapshot?.current_state?.location;
    if (typeof location === "string" && location.trim()) {
      locations.push(location.trim());
    }
  }
  const uniqueLocations = [...new Set(locations)];
  return Object.fromEntries(
    uniqueLocations.map((location, index) => [
      location,
      LOCATION_COLORS[index % LOCATION_COLORS.length],
    ]),
  );
}

function buildStorageAtlas(input) {
  const sessionOrder = [
    "source_path",
    "current_tick_label",
    "current_timeline_index",
    "arc_state",
    "agents",
    "pending_world_events",
    "pending_background_jobs",
    "append_only_log",
    "metadata",
  ];
  const discoveredKeys = Object.keys(input.session || {});
  const sessionKeys = [
    ...sessionOrder.filter((key) => discoveredKeys.includes(key)),
    ...discoveredKeys.filter((key) => !sessionOrder.includes(key)).sort(),
  ];
  const sessionShape = sessionKeys.map((key) => {
    const value = input.session?.[key];
    const meta = SESSION_FIELD_META[key] || {};
    return {
      key,
      role: meta.role || "Field",
      description: meta.description || "Top-level session field.",
      kind: valueKind(value),
      shape: describeValueShape(value),
    };
  });
  const appendCounts = Object.fromEntries(
    LOG_FAMILY_META.map((family) => [family.key, Array.isArray(input.appendOnly?.[family.key]) ? input.appendOnly[family.key].length : 0]),
  );
  const totalLogEntries = Object.values(appendCounts).reduce((sum, count) => sum + Number(count || 0), 0);
  const stateDimensions = summarizeCounts(input.stateChanges.map((entry) => String(entry.dimension || "unknown")));
  const layers = STORAGE_LAYER_CATALOG.map((layer) => ({
    ...layer,
    countLabel: layerCountLabel(layer.id, {
      sessionShape,
      totalLogEntries,
      appendCounts,
    }),
    exampleItems: layerExampleItems(layer.id, {
      sessionShape,
      appendCounts,
    }),
  }));
  const logFamilies = LOG_FAMILY_META.map((family) => ({
    ...family,
    count: appendCounts[family.key] || 0,
  }));
  const sqlTables = SQL_TABLE_CATALOG.map((table) => ({
    ...table,
    currentCount: currentSqlTableCount(table.id, input),
  }));
  return {
    rawBytes: Number(input.rawBytes || 0),
    sessionPath: input.sessionPath,
    sessionShape,
    logFamilies,
    sqlTables,
    layers,
    appendCounts,
    totalLogEntries,
    liveAgentCount: input.characters.length,
    pendingWorldEventCount: Number(input.pendingWorldEventCount || 0),
    backgroundJobCount: Number(input.backgroundJobCount || 0),
    stateDimensions,
    replayKey: [
      {
        field: "tick",
        detail: "Human-readable step label or snapshot name.",
      },
      {
        field: "timeline_index",
        detail: "Sortable story-time axis used by replay and scheduling.",
      },
      {
        field: "event_sequence",
        detail: "Tie-breaker for multiple writes at the same timeline index.",
      },
    ],
    agentStaticFields: AGENT_STATIC_FIELDS,
    agentDynamicFields: AGENT_DYNAMIC_FIELDS,
    realityChecks: [
      "Primary persistence is the session checkpoint JSON, not the SQL tables.",
      "Worlds are stored as aggregate snapshots and event queues, not as first-class world rows.",
      "Entity representations are latest-only in the SQL mirror rather than fully time-versioned.",
    ],
  };
}

function layerCountLabel(layerId, input) {
  if (layerId === "artifacts") {
    return "4 artifact families";
  }
  if (layerId === "session") {
    return `${input.sessionShape.length} top-level fields`;
  }
  if (layerId === "append") {
    return `${formatCount(input.totalLogEntries)} rows across ${Object.keys(input.appendCounts).length} buckets`;
  }
  if (layerId === "postgres") {
    return `${SQL_TABLE_CATALOG.length} documented tables`;
  }
  return "";
}

function layerExampleItems(layerId, input) {
  if (layerId === "artifacts") {
    return STORAGE_LAYER_CATALOG.find((layer) => layer.id === "artifacts")?.examples || [];
  }
  if (layerId === "session") {
    return input.sessionShape.slice(0, 5).map((field) => field.key);
  }
  if (layerId === "append") {
    return LOG_FAMILY_META
      .filter((family) => Number(input.appendCounts[family.key] || 0) > 0)
      .sort((left, right) => (input.appendCounts[right.key] || 0) - (input.appendCounts[left.key] || 0))
      .slice(0, 5)
      .map((family) => family.label);
  }
  if (layerId === "postgres") {
    return SQL_TABLE_CATALOG.slice(0, 5).map((table) => table.id);
  }
  return [];
}

function currentSqlTableCount(tableId, input) {
  if (tableId === "characters") {
    return input.characters.length;
  }
  if (tableId === "state_change_log") {
    return input.stateChanges.length;
  }
  if (tableId === "goal_stack") {
    return input.goalStacks.length;
  }
  if (tableId === "relationship_log") {
    return input.relationships.length;
  }
  if (tableId === "episodic_memory") {
    return input.memories.length;
  }
  if (tableId === "event_log") {
    return input.loggedEvents.length;
  }
  if (tableId === "world_snapshot") {
    return input.snapshots.length;
  }
  if (tableId === "entity_representation") {
    return Array.isArray(input.appendOnly?.entity_representations) ? input.appendOnly.entity_representations.length : 0;
  }
  if (tableId === "simulation_session") {
    return 1;
  }
  return null;
}

function summarizeCounts(values) {
  const counts = new Map();
  for (const value of values) {
    if (!value) {
      continue;
    }
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
}

function valueKind(value) {
  if (Array.isArray(value)) {
    return "array";
  }
  if (value && typeof value === "object") {
    return "object";
  }
  return typeof value;
}

function describeValueShape(value) {
  if (Array.isArray(value)) {
    return `${formatCount(value.length)} ${pluralize("item", value.length)}`;
  }
  if (value && typeof value === "object") {
    return `${formatCount(Object.keys(value).length)} ${pluralize("key", Object.keys(value).length)}`;
  }
  if (typeof value === "string") {
    return value ? "string" : "empty string";
  }
  if (typeof value === "number") {
    return "number";
  }
  if (typeof value === "boolean") {
    return "boolean";
  }
  return "empty";
}

function render() {
  if (!state.model) {
    return;
  }
  root.className = "app-shell";
  root.dataset.mode = state.mode;

  const visibleCharacters = getVisibleCharacters();
  const narrative = getNarrativeAt(state.tick);
  const tensionSeries = buildTensionSeries();
  const currentBeat = getMostRecentLoggedItem();
  const nextBeat = getUpcomingItems(1)[0] || null;
  const currentTickScale = formatTickScale(state.tick, state.model);
  const currentStepLabel = formatCurrentStep(state.tick, state.model);
  const llmIssueSummary = summarizeLlmIssues(state.tick);
  if (PAGE_MODE === "atlas") {
    root.innerHTML = renderAtlasPage({
      llmIssueSummary,
      currentTickScale,
      currentStepLabel,
    });
  } else {
    root.innerHTML = renderStoryPage({
      visibleCharacters,
      narrative,
      tensionSeries,
      currentBeat,
      nextBeat,
      currentTickScale,
      currentStepLabel,
      llmIssueSummary,
    });
  }

  bindEvents();
}

function renderAtlasPage(context) {
  return `
    <div class="workspace">
      ${renderPageSwitch()}
      <header class="header header--masthead">
        <div class="header__title">
          <p class="eyebrow">Dreamdive Data Atlas</p>
          <h1>How The Simulation Is Stored</h1>
          <p class="subtitle">
            ${escapeHtml(buildAtlasSubtitle())}
          </p>
        </div>
        <div class="header__status">
          <div class="snapshot-tag">Story time ${escapeHtml(formatTick(state.tick))}${context.currentStepLabel ? ` · ${escapeHtml(context.currentStepLabel)}` : ""}${context.currentTickScale ? ` · ${escapeHtml(context.currentTickScale)}` : ""}</div>
          <div class="header-meta">
            ${renderAtlasHeaderMeta(context.llmIssueSummary)}
          </div>
        </div>
      </header>

      <main class="dashboard">
        ${renderDataAtlas()}
      </main>
    </div>
  `;
}

function renderStoryPage(context) {
  return `
    <div class="workspace">
      ${renderPageSwitch()}
      <header class="header header--masthead">
        <div class="header__title">
          <p class="eyebrow">Visualization Layer</p>
          <h1>${escapeHtml(state.model.title)}</h1>
          <p class="subtitle">
            ${escapeHtml(buildSubtitle(context.narrative))}
          </p>
        </div>
        <div class="header__status">
          <div class="snapshot-tag">Story time ${escapeHtml(formatTick(state.tick))}${context.currentStepLabel ? ` · ${escapeHtml(context.currentStepLabel)}` : ""}${context.currentTickScale ? ` · ${escapeHtml(context.currentTickScale)}` : ""}</div>
          <div class="header-meta">
            ${renderStoryHeaderMeta(context.llmIssueSummary, context.visibleCharacters.length)}
          </div>
        </div>
      </header>

      <section class="control-ribbon">
        <div class="control-card control-card--playback">
          <div class="control-row">
            <label>Playback</label>
            <button class="button ${state.isPlaying ? "" : "button--soft"}" data-action="play-toggle">
              ${state.isPlaying ? "Pause" : "Play"}
            </button>
            <button class="button button--soft" data-action="reset-cursor">Reset</button>
            <button class="button button--soft" data-action="jump-now">Jump To Latest</button>
          </div>
          <div class="slider-row">
            <div class="range-wrap">
              <input
                type="range"
                min="${state.model.minTick}"
                max="${state.model.maxTick}"
                value="${state.tick}"
                step="1"
                data-action="scrub"
              />
              <output>${escapeHtml(formatTickLabel(state.tick, state.model))}</output>
            </div>
            <div class="control-row">
              <label for="speed-select">Speed</label>
              <select id="speed-select" data-action="speed-select">
                ${[1, 2, 4, 8]
                  .map(
                    (speed) => `
                      <option value="${speed}" ${speed === state.playSpeed ? "selected" : ""}>
                        ${speed}x
                      </option>
                    `,
                  )
                  .join("")}
              </select>
            </div>
          </div>
        </div>

        <div class="control-card control-card--mode">
          <div class="control-row">
            <label>Reading mode</label>
            <div class="mode-toggle">
              <button class="${state.mode === "external" ? "is-selected" : ""}" data-action="mode" data-mode="external">
                External
              </button>
              <button class="${state.mode === "internal" ? "is-selected" : ""}" data-action="mode" data-mode="internal">
                Internal
              </button>
            </div>
          </div>
          <p class="subtitle">
            ${escapeHtml(
              state.mode === "external"
                ? "Stay on visible action, movement, and consequences."
                : "Bring goals, emotion, and subtext into the frame.",
            )}
          </p>
        </div>

        <div class="control-card control-card--filters">
          <div class="control-row">
            <label>Cast in frame</label>
            <p class="control-note">${escapeHtml(`${context.visibleCharacters.length} of ${state.model.characters.length} visible`)}</p>
          </div>
          <div class="character-filter">
            <button class="chip ${context.visibleCharacters.length === state.model.characters.length ? "is-active" : ""}" data-action="show-all">
              All characters
            </button>
            ${state.model.characters
              .map(
                (character) => `
                  <button
                    class="chip ${state.visibleCharacterIds.has(character.id) ? "is-active" : ""}"
                    data-action="toggle-character"
                    data-character-id="${escapeHtml(character.id)}"
                  >
                    ${escapeHtml(character.name)}
                  </button>
                `,
              )
              .join("")}
          </div>
        </div>
      </section>

      <main class="dashboard">
        <section class="story-jump">
          <a class="story-jump__link" href="${escapeHtml(buildPageHref("atlas"))}">
            Open the Data Atlas for the accurate storage schema, table inventory, and replay model.
          </a>
        </section>

        <section class="stage-grid">
          <section class="card story-stage story-stage--lead">
            <div class="card__body">
              <p class="card__kicker">Story now</p>
              <h2 class="hero-title">Current reading</h2>
              <p class="card__summary">
                ${escapeHtml(buildHeroSummary(context.narrative, context.nextBeat))}
              </p>
              <div class="story-signals">
                ${renderStorySignal("Current phase", humanizeSlug(context.narrative.current_phase || "setup"), `${(context.narrative.unresolved_threads || []).length} unresolved thread${(context.narrative.unresolved_threads || []).length === 1 ? "" : "s"}`)}
                ${renderStorySignal("Shared pressure", formatPercent(context.narrative.tension_level || 0), context.currentStepLabel || "Step not recorded")}
                ${renderStorySignal("Scenes on record", String(state.model.loggedEvents.length), state.model.loggedEvents.length ? "Committed event markers" : "No committed scenes yet")}
                ${renderStorySignal("Story horizon", formatTick(state.model.maxTick), context.currentTickScale || "Tick span not recorded")}
              </div>
              <div class="beat-pair">
                ${renderBeatCard("Last committed scene", context.currentBeat, "The simulation is still in opening position.")}
                ${renderBeatCard("On deck", context.nextBeat, "No future beat is scheduled beyond this cursor.")}
              </div>
              <div class="thread-cluster">
                <span class="thread-cluster__label">Unresolved threads</span>
                <div class="pill-row">
                  ${renderThreadPills(context.narrative.unresolved_threads)}
                </div>
              </div>
            </div>
          </section>

          <div class="stage-rail">
            <section class="card story-note">
              <div class="card__body">
                <p class="card__kicker">Lens</p>
                <h2 class="card__title">${escapeHtml(state.mode === "external" ? "Observable world" : "Interior world")}</h2>
                <p class="card__summary">
                  ${escapeHtml(
                    state.mode === "external"
                      ? "Read this pass the way another character would: visible motion, placement, and outcomes."
                      : "Read it as a novelist or editor would: motive, suppression, and emotional pressure stay visible.",
                  )}
                </p>
                <div class="mode-brief mode-brief--${state.mode}">
                  <strong>${escapeHtml(state.mode === "external" ? "DO" : "THINK")}</strong>
                  <span>${escapeHtml(state.mode === "external" ? "Action-first surface" : "Subtext-first depth")}</span>
                </div>
                <p class="footer-note">${escapeHtml(buildModeSupportLine())}</p>
              </div>
            </section>

            <section class="card story-note">
              <div class="card__body">
                <p class="card__kicker">Forecast</p>
                <h2 class="card__title">Story runway</h2>
                <p class="card__summary">${escapeHtml(buildRunwaySummary(context.nextBeat))}</p>
                <div class="forecast-list">
                  ${renderForecastList(3)}
                </div>
              </div>
            </section>
          </div>
        </section>

        ${renderLlmIssueSection(context.llmIssueSummary)}

        <section class="card timeline-card">
          <div class="card__body">
            <div class="section-head">
              <div>
                <p class="card__kicker">Story map</p>
                <h2 class="card__title">Master Timeline</h2>
                <p class="card__summary">
                  Past scenes appear as filled markers. Scheduled beats remain outlined so the dashboard can hold the future story horizon before the session catches up.
                </p>
              </div>
              <div class="section-pulse">
                ${renderPulseTag("Committed", context.currentBeat ? `${itemLabel(context.currentBeat)} · ${formatTick(context.currentBeat.timeline_index)}` : "Waiting for the first committed scene")}
                ${renderPulseTag("On deck", context.nextBeat ? `${itemLabel(context.nextBeat)} · ${formatTick(context.nextBeat.timeline_index)}` : "No scheduled beat beyond the cursor")}
              </div>
            </div>
            <div class="chart-shell">
              ${renderTimelineSvg()}
            </div>
            <div class="legend">
              <span><i class="swatch" style="background:${EVENT_COLORS.goal_collision}"></i> Spotlight / goal collision</span>
              <span><i class="swatch" style="background:${EVENT_COLORS.solo}"></i> Solo seed</span>
              <span><i class="swatch" style="background:${EVENT_COLORS.world}"></i> World event</span>
              <span><i class="swatch swatch--outlined"></i> Scheduled but not yet simulated</span>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card__body">
            <p class="card__kicker">Pressure</p>
            <h2 class="card__title">Tension Curve</h2>
            <div class="phase-banner">
              <span>${escapeHtml(humanizeSlug(context.narrative.current_phase || "setup"))}</span>
              <span>${escapeHtml(`${(context.narrative.unresolved_threads || []).length} threads live`)}</span>
            </div>
            <p class="card__summary">
              The curve reads from recorded world snapshots when they exist, and falls back to the initial and current arc state while the session is still near its opening beat.
            </p>
            <div class="chart-shell">
              ${renderTensionSvg(context.tensionSeries)}
            </div>
            ${
              context.tensionSeries.length < 2
                ? `<p class="empty-note">Run additional simulation ticks to turn this opening-state line into a real dramatic contour.</p>`
                : ""
            }
          </div>
        </section>

        <section class="card relationship-card">
          <div class="card__body">
            <p class="card__kicker">Affinity</p>
            <h2 class="card__title">Relationship Graph</h2>
            <p class="card__summary">
              Force-directed scatter plot layout: characters are positioned dynamically based on relational pressures.
            </p>
            <div class="relationship-panel">
              <div class="chart-shell chart-shell--relationship">
                ${renderRelationshipSvg(context.visibleCharacters)}
              </div>
              <div class="relationship-controls">
                <div class="legend-group">
                  <span>Edges:</span>
                  <div class="legend-item"><span class="legend-line" style="background: #B88E4B; height: 3px;"></span> Alliance</div>
                  <div class="legend-item"><span class="legend-line" style="border-top: 3px dashed #517498; background: transparent;"></span> Neutral</div>
                  <div class="legend-item"><span class="legend-line" style="background: #8c2f2a; height: 3px;"></span> Hostile</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card__body">
            <p class="card__kicker">Cast motion</p>
            <h2 class="card__title">Character Activity Traces</h2>
            <p class="card__summary">
              Each lane shows location continuity across the shared time axis. Internal mode adds goal focus and richer state text at the cursor.
            </p>
            <div class="swimlane">
              ${context.visibleCharacters.map((character) => renderSwimlaneRow(character)).join("")}
            </div>
          </div>
        </section>
      </main>
    </div>

    <aside class="slide-panel ${state.panel ? "is-open" : ""}">
      <div class="slide-panel__inner">
        <div class="slide-panel__body">
          ${state.panel ? renderPanel() : renderPanelPlaceholder()}
        </div>
      </div>
    </aside>
  `;
}

function renderPageSwitch() {
  return `
    <nav class="page-switch" aria-label="Visualization pages">
      <a class="page-switch__link ${PAGE_MODE === "story" ? "is-active" : ""}" href="${escapeHtml(buildPageHref("story"))}">
        Story View
      </a>
      <a class="page-switch__link ${PAGE_MODE === "atlas" ? "is-active" : ""}" href="${escapeHtml(buildPageHref("atlas"))}">
        Data Atlas
      </a>
    </nav>
  `;
}

function renderDataAtlas() {
  const atlas = state.model.storageAtlas;
  return `
    <section class="atlas-grid">
      <section class="card atlas-card atlas-card--lead">
        <div class="card__body">
          <p class="card__kicker">Storage model</p>
          <h2 class="hero-title">The current architecture is checkpoint-first, not database-first.</h2>
          <p class="card__summary">
            Dreamdive persists one live session checkpoint JSON containing denormalized agent snapshots plus append-only history. Replay uses a three-part key to recover earlier state, and the SQL schema exists as an optional mirror for queries, embeddings, and future tooling.
          </p>
          <div class="story-signals">
            ${renderStorySignal("Primary store", "Session JSON", `${atlas.sessionShape.length} top-level fields in the live checkpoint`)}
            ${renderStorySignal("Replay key", "tick / timeline / sequence", "Time is reconstructed from ordered log rows")}
            ${renderStorySignal("History", `${formatCount(atlas.totalLogEntries)} rows`, `${atlas.logFamilies.length} append-only log families`)}
            ${renderStorySignal("SQL mirror", `${atlas.sqlTables.length} tables`, "Optional Postgres path, not the default source of truth")}
          </div>
          <div class="atlas-flow">
            ${renderAtlasFlowStep("1", "Extract source artifacts", "Static source facts land in artifact JSON files.")}
            ${renderAtlasFlowStep("2", "Build session checkpoint", "Live agents, arc state, and queues are packed into one session payload.")}
            ${renderAtlasFlowStep("3", "Append temporal rows", "Changes, goals, memories, events, and diagnostics accumulate over time.")}
            ${renderAtlasFlowStep("4", "Replay or mirror", "The UI replays history; optional SQL mirrors the same shape for queries.")}
          </div>
        </div>
      </section>

      <div class="atlas-rail">
        <section class="card atlas-card atlas-brief">
          <div class="card__body">
            <p class="card__kicker">Reality check</p>
            <h2 class="card__title">What is first-class right now</h2>
            <div class="atlas-note-list">
              ${atlas.realityChecks.map((item) => `<article class="atlas-note">${escapeHtml(item)}</article>`).join("")}
            </div>
          </div>
        </section>

        <section class="card atlas-card atlas-brief">
          <div class="card__body">
            <p class="card__kicker">Loaded evidence</p>
            <h2 class="card__title">Current session facts</h2>
            <div class="atlas-evidence-list">
              <div class="atlas-evidence">
                <span>Path</span>
                <strong>${escapeHtml(state.model.sessionPath)}</strong>
              </div>
              <div class="atlas-evidence">
                <span>Checkpoint size</span>
                <strong>${escapeHtml(formatBytes(atlas.rawBytes))}</strong>
              </div>
              <div class="atlas-evidence">
                <span>Pending world events</span>
                <strong>${escapeHtml(formatCount(atlas.pendingWorldEventCount))}</strong>
              </div>
              <div class="atlas-evidence">
                <span>Background jobs</span>
                <strong>${escapeHtml(formatCount(atlas.backgroundJobCount))}</strong>
              </div>
            </div>
          </div>
        </section>
      </div>
    </section>

    <section class="atlas-strip">
      ${renderAtlasMetric("Live agents", formatCount(atlas.liveAgentCount), "Current runtime snapshots stored under agents")}
      ${renderAtlasMetric("Append rows", formatCount(atlas.totalLogEntries), "All active append-only buckets in this checkpoint")}
      ${renderAtlasMetric("State dimensions", formatCount(atlas.stateDimensions.length), atlas.stateDimensions.length ? `Most frequent: ${humanizeSlug(atlas.stateDimensions[0].label)}` : "No temporal dimensions recorded yet")}
      ${renderAtlasMetric("Future horizon", formatCount(state.model.scheduledEvents.length), "Scheduled world beats that have not been committed")}
    </section>

    <section class="analysis-grid">
      <section class="card atlas-card">
        <div class="card__body">
          <p class="card__kicker">Storage layers</p>
          <h2 class="card__title">Where the data lives</h2>
          <p class="card__summary">
            The system layers extracted source facts, a checkpoint payload, append-only logs, and an optional SQL mirror. The checkpoint and its logs are the operative runtime truth.
          </p>
          <div class="layer-grid">
            ${atlas.layers.map((layer) => renderStorageLayer(layer)).join("")}
          </div>
        </div>
      </section>

      <section class="card atlas-card">
        <div class="card__body">
          <p class="card__kicker">Temporal model</p>
          <h2 class="card__title">How time and replay work</h2>
          <p class="card__summary">
            Every meaningful historical row is ordered by replay metadata. To reconstruct an earlier moment, the system replays rows at or before the target story cursor and keeps the latest write per dimension.
          </p>
          <div class="replay-key">
            ${atlas.replayKey.map((entry) => `
              <div class="replay-key__item">
                <strong>${escapeHtml(entry.field)}</strong>
                <p>${escapeHtml(entry.detail)}</p>
              </div>
            `).join("")}
          </div>
          <div class="replay-grid">
            ${renderReplayStep("Load live checkpoint", "Start from the current session payload and its denormalized agent snapshots.")}
            ${renderReplayStep("Filter rows by cursor", "Read append-only rows whose timeline index is at or before the target time.")}
            ${renderReplayStep("Apply latest wins", "For each dimension or relation edge, the last row in replay order becomes the visible state.")}
          </div>
          <p class="footer-note">
            Tick size is variable, so <code>timeline_index</code> is the real sortable story-time axis. <code>event_sequence</code> breaks ties when multiple writes happen at the same story minute.
          </p>
        </div>
      </section>
    </section>

    <section class="analysis-grid">
      <section class="card atlas-card">
        <div class="card__body">
          <p class="card__kicker">Session shape</p>
          <h2 class="card__title">Top-level checkpoint payload</h2>
          <p class="card__summary">
            The live session checkpoint is the object this page loads. These are the top-level fields currently present in the active session file.
          </p>
          <div class="shape-grid">
            ${atlas.sessionShape.map((field) => renderSessionShapeItem(field)).join("")}
          </div>
          <div class="shape-split">
            <article class="shape-card">
              <h3>Inside each agent snapshot</h3>
              <div class="pill-row">
                ${["identity", "current_state", "goals", "working_memory", "relationships", "inferred_state"].map((field) => `<span class="pill pill--mono">${escapeHtml(field)}</span>`).join("")}
              </div>
              <p class="footer-note">This is a denormalized current-state snapshot, not the full history by itself.</p>
            </article>
            <article class="shape-card">
              <h3>Inside append_only_log</h3>
              <div class="pill-row">
                ${atlas.logFamilies.map((family) => `<span class="pill pill--mono">${escapeHtml(family.label)}</span>`).join("")}
              </div>
              <p class="footer-note">These buckets are what make branching, replay, and inspection across time possible.</p>
            </article>
          </div>
        </div>
      </section>

      <section class="card atlas-card">
        <div class="card__body">
          <p class="card__kicker">Agents</p>
          <h2 class="card__title">Static vs dynamic agent data</h2>
          <p class="card__summary">
            Agents mix relatively static identity fields with dynamic runtime state. Only some dynamic fields are currently written as explicit time-series rows; others are derived into the current snapshot.
          </p>
          <div class="shape-split">
            <article class="shape-card">
              <h3>Mostly static / identity-ish</h3>
              <ul class="shape-list">
                ${atlas.agentStaticFields.map((field) => `<li><code>${escapeHtml(field)}</code></li>`).join("")}
              </ul>
            </article>
            <article class="shape-card">
              <h3>Dynamic / runtime-facing</h3>
              <ul class="shape-list">
                ${atlas.agentDynamicFields.map((field) => `<li><code>${escapeHtml(field)}</code></li>`).join("")}
              </ul>
            </article>
          </div>
          <div class="dimension-band">
            ${atlas.stateDimensions.length
              ? atlas.stateDimensions.map((entry) => `<span class="dimension-chip">${escapeHtml(humanizeSlug(entry.label))} · ${escapeHtml(formatCount(entry.count))}</span>`).join("")
              : `<span class="dimension-chip">No explicit state dimensions recorded yet</span>`}
          </div>
          <p class="footer-note">
            These chips reflect the dimensions that are explicitly time-versioned in the current checkpoint. Everything else may still exist in the current snapshot, but not necessarily as its own replay log.
          </p>
        </div>
      </section>
    </section>

    <section class="card atlas-card">
      <div class="card__body">
        <p class="card__kicker">Append-only logs</p>
        <h2 class="card__title">Temporal buckets in the checkpoint</h2>
        <p class="card__summary">
          These are the actual log families carried inside <code>append_only_log</code>. Counts below come from the currently loaded session file.
        </p>
        <div class="log-grid">
          ${atlas.logFamilies.map((family) => renderLogFamilyCard(family)).join("")}
        </div>
      </div>
    </section>

    <section class="card atlas-card">
      <div class="card__body">
        <p class="card__kicker">SQL inventory</p>
        <h2 class="card__title">Documented database tables</h2>
        <p class="card__summary">
          This is the current SQL table catalog that mirrors or supplements the checkpoint model. It is grouped by purpose so the structure reads like a schema explorer instead of a flat migration dump.
        </p>
        <div class="table-groups">
          ${renderSqlGroups(atlas.sqlTables)}
        </div>
      </div>
    </section>
  `;
}

function renderAtlasFlowStep(index, title, detail) {
  return `
    <article class="atlas-flow__step">
      <span class="atlas-flow__index">${escapeHtml(index)}</span>
      <div>
        <strong>${escapeHtml(title)}</strong>
        <p>${escapeHtml(detail)}</p>
      </div>
    </article>
  `;
}

function renderAtlasMetric(label, value, detail) {
  return `
    <article class="atlas-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <p>${escapeHtml(detail)}</p>
    </article>
  `;
}

function renderStorageLayer(layer) {
  return `
    <article class="layer-card">
      <div class="layer-card__header">
        <span class="status-badge status-badge--${escapeHtml(layer.mode)}">${escapeHtml(layer.mode)}</span>
        <strong>${escapeHtml(layer.label)}</strong>
      </div>
      <p>${escapeHtml(layer.description)}</p>
      <div class="layer-card__meta">
        <span>${escapeHtml(layer.countLabel)}</span>
      </div>
      <div class="pill-row">
        ${layer.exampleItems.map((item) => `<span class="pill pill--mono">${escapeHtml(item)}</span>`).join("")}
      </div>
    </article>
  `;
}

function renderReplayStep(title, detail) {
  return `
    <article class="replay-step">
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(detail)}</p>
    </article>
  `;
}

function renderSessionShapeItem(field) {
  return `
    <article class="shape-item">
      <div class="shape-item__header">
        <strong><code>${escapeHtml(field.key)}</code></strong>
        <span>${escapeHtml(field.kind)}</span>
      </div>
      <p>${escapeHtml(field.description)}</p>
      <div class="shape-item__meta">
        <span>${escapeHtml(field.role)}</span>
        <span>${escapeHtml(field.shape)}</span>
      </div>
    </article>
  `;
}

function renderLogFamilyCard(family) {
  return `
    <article class="log-card ${family.count ? "" : "log-card--empty"}">
      <div class="log-card__header">
        <div>
          <strong><code>${escapeHtml(family.label)}</code></strong>
          <span>${escapeHtml(family.kind)}</span>
        </div>
        <span class="log-card__count">${escapeHtml(formatCount(family.count))}</span>
      </div>
      <p>${escapeHtml(family.description)}</p>
      <div class="pill-row">
        ${family.fields.map((field) => `<span class="pill pill--mono">${escapeHtml(field)}</span>`).join("")}
      </div>
    </article>
  `;
}

function renderSqlGroups(tables) {
  const groups = groupBy(tables, "group");
  return Object.entries(groups)
    .map(
      ([group, groupTables]) => `
        <section class="table-group">
          <div class="table-group__header">
            <h3>${escapeHtml(group)}</h3>
            <span>${escapeHtml(`${groupTables.length} ${pluralize("table", groupTables.length)}`)}</span>
          </div>
          <div class="table-grid">
            ${groupTables.map((table) => renderSqlTableCard(table)).join("")}
          </div>
        </section>
      `,
    )
    .join("");
}

function renderSqlTableCard(table) {
  const countLabel = table.currentCount == null ? "not materialized in current session" : `${formatCount(table.currentCount)} loaded rows / objects`;
  return `
    <article class="table-card">
      <div class="table-card__header">
        <div>
          <strong><code>${escapeHtml(table.id)}</code></strong>
          <span>${escapeHtml(table.kind)}</span>
        </div>
        <span class="table-card__count">${escapeHtml(countLabel)}</span>
      </div>
      <p>${escapeHtml(table.description)}</p>
      <div class="pill-row">
        ${table.fields.map((field) => `<span class="pill pill--mono">${escapeHtml(field)}</span>`).join("")}
      </div>
      ${table.note ? `<p class="footer-note">${escapeHtml(table.note)}</p>` : ""}
    </article>
  `;
}

function renderStorySignal(label, value, detail) {
  return `
    <div class="signal-card">
      <span class="signal-card__label">${escapeHtml(label)}</span>
      <strong class="signal-card__value">${escapeHtml(value)}</strong>
      <p class="signal-card__detail">${escapeHtml(detail)}</p>
    </div>
  `;
}

function renderBeatCard(label, item, emptyMessage) {
  if (!item) {
    return `
      <article class="beat-card beat-card--empty">
        <span class="beat-card__eyebrow">${escapeHtml(label)}</span>
        <strong>${escapeHtml(emptyMessage)}</strong>
      </article>
    `;
  }
  const summary = item.outcome_summary || item.description || (item.event_kind === "scheduled"
    ? "Setup exists, but the outcome has not been simulated yet."
    : "This scene has been committed to the timeline.");
  return `
    <button class="beat-card beat-card--${item.event_kind}" data-action="open-event" data-event-id="${escapeHtml(item.event_id)}">
      <span class="beat-card__eyebrow">${escapeHtml(label)}</span>
      <strong>${escapeHtml(itemLabel(item))}</strong>
      <p class="meta-line">${escapeHtml(formatTimelineMeta(item.timeline_index, item.location || "Unplaced", item.event_kind === "scheduled" ? "scheduled beat" : "logged scene"))}</p>
      <p>${escapeHtml(truncate(summary, 140))}</p>
    </button>
  `;
}

function renderPulseTag(label, value) {
  return `
    <div class="pulse-tag">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function renderStoryHeaderMeta(summary, visibleCount) {
  const items = [
    state.model.metadata.chapter_id ? `Chapter ${state.model.metadata.chapter_id}` : "",
    visibleCount ? `${visibleCount} cast in view` : "",
    summary.totalCount ? `${summary.totalCount} LLM warnings recorded` : "No LLM warnings recorded",
  ].filter(Boolean);
  return items.map((item) => `<span class="header-meta__item">${escapeHtml(item)}</span>`).join("");
}

function renderAtlasHeaderMeta(summary) {
  const items = [
    "Session-first checkpoint",
    `${state.model.storageAtlas.logFamilies.length} log families`,
    `${state.model.storageAtlas.sqlTables.length} SQL tables documented`,
    summary.totalCount ? `${summary.totalCount} LLM warnings recorded` : "No LLM warnings recorded",
  ].filter(Boolean);
  return items.map((item) => `<span class="header-meta__item">${escapeHtml(item)}</span>`).join("");
}

function renderLlmIssueSection(summary) {
  if (!summary.totalCount) {
    return "";
  }
  const issues = summary.visibleIssues.slice(-3).reverse();
  return `
    <section class="card diagnostics-card ${state.showDiagnostics ? "diagnostics-card--expanded" : ""}">
      <div class="card__body">
        <p class="card__kicker">System watch</p>
        <div class="diagnostics-header">
          <div class="diagnostics-copy">
            <p class="diagnostics-inline">
              ${escapeHtml(buildCollapsedLlmMessage(summary))}
            </p>
          </div>
          <div class="diagnostics-header__controls">
            <div class="diagnostics-badge">${escapeHtml(`${summary.visibleCount}/${summary.totalCount}`)}</div>
            <button class="button button--soft diagnostics-toggle" data-action="toggle-diagnostics">
              ${state.showDiagnostics ? "Hide details" : "Show details"}
            </button>
          </div>
        </div>
        ${
          state.showDiagnostics && issues.length
            ? `
              <div class="diagnostics-expanded">
                <p class="card__summary">
                  ${escapeHtml(buildLlmWarningSummary(summary))}
                </p>
                <div class="diagnostics-list">
                  ${issues.map((issue) => renderLlmIssueItem(issue)).join("")}
                </div>
              </div>
            `
            : state.showDiagnostics
              ? `
              <div class="diagnostics-expanded">
                <p class="card__summary">
                  ${escapeHtml(buildLlmWarningSummary(summary))}
                </p>
                <p class="empty-note">
                  No warnings have happened yet at this cursor. Later steps in the session do record structured-output failures.
                </p>
              </div>
            `
              : ""
        }
      </div>
    </section>
  `;
}

function renderLlmIssueItem(issue) {
  const metaParts = [
    formatTimelineMeta(issue.timeline_index, humanizeSlug(issue.phase || "tick")),
    issue.profile_name || "",
    issue.stage ? humanizeSlug(issue.stage) : "",
    issue.character_id ? humanizeSlug(issue.character_id) : "",
  ].filter(Boolean);
  const preview = issue.response_was_empty
    ? "Provider returned an empty response body."
    : issue.response_preview || issue.error_message || "The response could not be validated.";
  return `
    <article class="diagnostic-item">
      <div class="diagnostic-item__header">
        <strong>${escapeHtml(humanizePromptName(issue.prompt_name))}</strong>
        <span>${escapeHtml(issue.error_type || issue.schema_name || "Warning")}</span>
      </div>
      <p class="meta-line">${escapeHtml(metaParts.join(" · "))}</p>
      <p>${escapeHtml(issue.error_message || "Structured output validation failed.")}</p>
      <p class="diagnostic-item__preview">${escapeHtml(truncate(preview, 220))}</p>
    </article>
  `;
}

function renderThreadPills(threads) {
  if (!Array.isArray(threads) || !threads.length) {
    return `<span class="pill">No active unresolved thread</span>`;
  }
  return threads
    .slice(0, 5)
    .map((thread) => `<span class="pill">${escapeHtml(humanizeSlug(thread))}</span>`)
    .join("");
}

function renderForecastList(limit) {
  const items = getUpcomingItems(limit);
  if (!items.length) {
    return `
      <div class="forecast-item">
        <strong>No future beat is scheduled beyond this cursor.</strong>
        <p>The dashboard has caught up with the current story horizon.</p>
      </div>
    `;
  }
  return items
    .map(
      (item) => `
        <button class="forecast-item" data-action="open-event" data-event-id="${escapeHtml(item.event_id)}">
          <strong>${escapeHtml(itemLabel(item))}</strong>
          <p>${escapeHtml(formatTimelineMeta(item.timeline_index, item.location || "Unplaced"))}</p>
        </button>
      `,
    )
    .join("");
}

function renderRelationshipLedger(visibleCharacters) {
  const visibleIds = new Set(visibleCharacters.map((character) => character.id));
  const edges = getRelationshipsAt(state.tick)
    .filter((edge) => visibleIds.has(edge.from_character_id) && visibleIds.has(edge.to_character_id))
    .sort((left, right) => relationshipStrength(right) - relationshipStrength(left))
    .slice(0, 6);
  if (!edges.length) {
    return `<p class="meta-line">No directed relationship update has been recorded yet at this cursor.</p>`;
  }
  return edges
    .map((edge) => {
      const from = state.model.characterById[edge.from_character_id]?.name || humanizeSlug(edge.from_character_id);
      const to = state.model.characterById[edge.to_character_id]?.name || humanizeSlug(edge.to_character_id);
      const accent = relationshipColor(edge.sentiment_shift, edge.trust_value);
      const reason = edge.reason || edge.justification || edge.summary || "";
      return `
        <article class="relationship-ledger__item" style="--relationship-accent:${accent};">
          <div class="relationship-ledger__header">
            <strong>${escapeHtml(`${from} → ${to}`)}</strong>
            <span class="relationship-ledger__score">${escapeHtml(`trust ${formatSignedDecimal(edge.trust_value || 0)}`)}</span>
          </div>
          <p class="relationship-ledger__sentiment">${escapeHtml(humanizeSlug(edge.sentiment_shift || "neutral"))}</p>
          ${
            reason
              ? `<p class="relationship-ledger__reason">${escapeHtml(truncate(reason, 120))}</p>`
              : `<p class="relationship-ledger__reason">${escapeHtml("No explicit reason note stored for this edge yet.")}</p>`
          }
        </article>
      `;
    })
    .join("");
}

function renderTimelineSvg() {
  const width = 1120;
  const height = 240;
  const left = 44;
  const right = 36;
  const top = 26;
  const bottom = 46;
  const trackY = 154;
  const innerWidth = width - left - right;
  const items = filteredTimelineItems();
  const ticks = pickAxisTicks(state.model.minTick, state.model.maxTick, 6);

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Master timeline">
      <defs>
        <linearGradient id="timeline-track" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="rgba(35,65,93,0.12)" />
          <stop offset="50%" stop-color="rgba(173,79,45,0.18)" />
          <stop offset="100%" stop-color="rgba(35,65,93,0.12)" />
        </linearGradient>
      </defs>
      <rect x="${left}" y="${trackY - 6}" width="${innerWidth}" height="12" rx="6" fill="url(#timeline-track)" />
      ${ticks
        .map((tick) => {
          const x = scaleTick(tick, width, left, right);
          return `
            <line x1="${x}" y1="${top}" x2="${x}" y2="${height - bottom + 8}" stroke="rgba(24,33,45,0.08)" stroke-dasharray="4 6" />
            <text class="timeline-axis-label" x="${x}" y="${height - 12}" fill="rgba(24,33,45,0.56)" text-anchor="middle" font-size="12">
              ${escapeHtml(formatTick(tick))}
            </text>
          `;
        })
        .join("")}
      ${items
        .map((item, index) => {
          const x = scaleTick(item.timeline_index, width, left, right);
          const color = markerColor(item);
          const markerY = trackY - 18 - (index % 3) * 26;
          const size = markerSize(item);
          const isScheduled = item.event_kind === "scheduled";
          const markerShape = renderMarkerShape({ x, y: markerY, size, color, isScheduled });
          return `
            <g data-action="open-event" data-event-id="${escapeHtml(item.event_id)}" class="timeline-marker">
              <line x1="${x}" y1="${markerY + size}" x2="${x}" y2="${trackY - 8}" stroke="${color}" stroke-width="1.5" stroke-dasharray="${isScheduled ? "4 4" : "0"}" />
              ${markerShape}
              <title>${escapeHtml(eventTooltip(item))}</title>
            </g>
          `;
        })
        .join("")}
      <line x1="${scaleTick(state.tick, width, left, right)}" y1="${top}" x2="${scaleTick(state.tick, width, left, right)}" y2="${height - bottom + 8}" stroke="${EVENT_COLORS.goal_collision}" stroke-width="2.5" />
    </svg>
  `;
}

function renderMarkerShape({ x, y, size, color, isScheduled }) {
  const stroke = `stroke="${color}" stroke-width="2"`;
  const fill = isScheduled ? `fill="transparent"` : `fill="${color}"`;
  return `<circle cx="${x}" cy="${y}" r="${size}" ${fill} ${stroke} />`;
}

function renderTensionSvg(series) {
  const width = 820;
  const height = 300;
  const left = 46;
  const right = 24;
  const top = 24;
  const bottom = 42;
  const innerWidth = width - left - right;
  const innerHeight = height - top - bottom;
  const safeSeries = series.length ? series : [{ tick: 0, tension: 0, phase: "setup" }];
  const points = safeSeries.map((point) => ({
    ...point,
    x: scaleTick(point.tick, width, left, right),
    y: top + innerHeight - point.tension * innerHeight,
  }));
  const polyline = points.map((point) => `${point.x},${point.y}`).join(" ");
  const ticks = pickAxisTicks(state.model.minTick, state.model.maxTick, 5);

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Tension curve">
      <defs>
        <linearGradient id="tension-line" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="${EVENT_COLORS.solo}" />
          <stop offset="100%" stop-color="${EVENT_COLORS.goal_collision}" />
        </linearGradient>
      </defs>
      ${[0, 0.25, 0.5, 0.75, 1]
        .map((level) => {
          const y = top + innerHeight - level * innerHeight;
          return `
            <line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="rgba(24,33,45,0.08)" />
            <text x="${left - 12}" y="${y + 4}" fill="rgba(24,33,45,0.52)" text-anchor="end" font-size="11">${Math.round(level * 100)}%</text>
          `;
        })
        .join("")}
      ${ticks
        .map((tick) => {
          const x = scaleTick(tick, width, left, right);
          return `
            <line x1="${x}" y1="${top}" x2="${x}" y2="${height - bottom}" stroke="rgba(24,33,45,0.05)" stroke-dasharray="4 6" />
            <text x="${x}" y="${height - 12}" fill="rgba(24,33,45,0.52)" text-anchor="middle" font-size="11">${escapeHtml(formatTick(tick))}</text>
          `;
        })
        .join("")}
      <polyline fill="none" stroke="url(#tension-line)" stroke-width="4" stroke-linejoin="round" stroke-linecap="round" points="${polyline}" />
      ${points
        .map(
          (point) => `
            <circle cx="${point.x}" cy="${point.y}" r="5" fill="${EVENT_COLORS.goal_collision}" />
            <title>${escapeHtml(`${formatTick(point.tick)} · ${humanizeSlug(point.phase)} · ${formatPercent(point.tension)}`)}</title>
          `,
        )
        .join("")}
      <line x1="${scaleTick(state.tick, width, left, right)}" y1="${top}" x2="${scaleTick(state.tick, width, left, right)}" y2="${height - bottom}" stroke="${EVENT_COLORS.goal_collision}" stroke-width="2" />
    </svg>
  `;
}

function renderRelationshipSvg(visibleCharacters) {
  const width = 960;
  const height = 480;
  const centerX = width / 2;
  const centerY = height / 2;
  const nodes = visibleCharacters.map((character) => {
    return {
      ...character,
      nodeRadius: 8,
      moodColor: "#4B76A0", // Uniform default node color for scatter plot
    };
  });
  
  const edgesRaw = getRelationshipsAt(state.tick)
    .filter((relationship) => {
      return state.visibleCharacterIds.has(relationship.from_character_id) && state.visibleCharacterIds.has(relationship.to_character_id);
    })
    .sort((left, right) => relationshipStrength(left) - relationshipStrength(right));

  const edgeKeys = new Set(edgesRaw.map((edge) => `${edge.from_character_id}::${edge.to_character_id}`));

  const links = edgesRaw.map(edge => ({
    ...edge,
    source: edge.from_character_id,
    target: edge.to_character_id
  }));

  // Setup D3 Force Layout Simulation synchronously
  const simulation = d3.forceSimulation(nodes)
    .force("charge", d3.forceManyBody().strength(-300)) // Repel force
    .force("center", d3.forceCenter(centerX, centerY)) // Center of SVG
    .force("link", d3.forceLink(links).id(d => d.id).distance(120)) // Link targets
    .force("collide", d3.forceCollide().radius(15).iterations(2)) // Avoid dense overlap
    .stop(); // Don't animate in DOM real-time

  // Spool simulation physics forward 300 steps explicitly to reach a stable static graph
  for (let i = 0; i < 300; ++i) simulation.tick();
  
  // Clamp node coordinates within SVG bounds minus padding
  const padding = 20;
  nodes.forEach(node => {
    node.x = Math.max(padding, Math.min(width - padding, node.x));
    node.y = Math.max(padding, Math.min(height - padding, node.y));
  });
  
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Relationship graph">
      <defs>
        <filter id="node-shadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000000" flood-opacity="0.3"/>
        </filter>
      </defs>
      <g>
        ${links
          .map((edge) => {
            // d3.forceLink replaces string sources with actual node objects
            const from = edge.source; 
            const to = edge.target;
            if (from == null || to == null) return "";

            const trustValue = Number(edge.trust_value || 0);
            
            let edgeColor = "#517498"; // Default Neutral Blue
            let isDashed = true;
            let strokeWidth = 1.5;
            
            if (trustValue > 0.3 || (edge.sentiment_shift && /(loyal|trust|respect|allied|positive)/.test(edge.sentiment_shift.toLowerCase()))) {
               edgeColor = "#B88E4B"; // Alliance Gold
               isDashed = false;
               strokeWidth = 2;
            } else if (trustValue < -0.3 || (edge.sentiment_shift && /(hostile|enmity|critical|conflict)/.test(edge.sentiment_shift.toLowerCase()))) {
               edgeColor = "#8c2f2a"; // Hostile Red
               isDashed = false;
               strokeWidth = 2;
            }

            const dx = to.x - from.x;
            const dy = to.y - from.y;
            
            const curvature = 0.25; 
            const cx = (from.x + to.x) / 2 - dy * curvature;
            const cy = (from.y + to.y) / 2 + dx * curvature;
            
            const hasReverse = edgeKeys.has(`${edge.to_character_id}::${edge.from_character_id}`);
            const finalCx = hasReverse ? (from.x + to.x) / 2 - dy * 0.35 : cx;
            const finalCy = hasReverse ? (from.y + to.y) / 2 + dx * 0.35 : cy;

            return `
              <g class="relationship-edge-group" style="cursor: pointer;">
                <!-- Target Visual Line -->
                <path d="M ${from.x} ${from.y} Q ${finalCx} ${finalCy} ${to.x} ${to.y}" 
                      fill="none" 
                      stroke="${edgeColor}" 
                      stroke-width="${strokeWidth}" 
                      stroke-opacity="0.8"
                      ${isDashed ? 'stroke-dasharray="4 4"' : ''} />
                      
                <!-- Thick Invisible Hitbox for Edge Hover -->
                <path d="M ${from.x} ${from.y} Q ${finalCx} ${finalCy} ${to.x} ${to.y}" 
                      fill="none" 
                      stroke="transparent" 
                      stroke-width="12" />
                <title>${escapeHtml(buildRelationshipTooltip(edge))}</title>
              </g>
            `;
          })
          .join("")}
      </g>
      <g>
        ${nodes
          .map((node) => {
            const roleText = node.identity?.domain_attributes?.role || "Unknown Role";
            return `
              <g class="node-group" transform="translate(${node.x},${node.y})" data-action="open-character" data-character-id="${escapeHtml(node.id)}" style="pointer-events: bounding-box; cursor: pointer;">
                <title>${escapeHtml(node.name)}\nRole: ${escapeHtml(roleText)}</title>
                <circle class="character-node" r="${node.nodeRadius}" fill="${node.moodColor}" filter="url(#node-shadow)"></circle>
                <circle class="character-node" r="${node.nodeRadius}" fill="none" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" />
              </g>
            `;
          })
          .join("")}
      </g>
    </svg>
  `;
}

function settleRelationshipLabels(nodes) {
  const groups = new Map();
  for (const node of nodes) {
    const bucket = groups.get(node.side) || [];
    bucket.push(node);
    groups.set(node.side, bucket);
  }
  for (const bucket of groups.values()) {
    bucket.sort((left, right) => left.labelY - right.labelY);
    let previousY = 48;
    for (const node of bucket) {
      node.labelY = Math.max(previousY, node.labelY);
      previousY = node.labelY + 34;
    }
    let maxY = 432;
    for (let index = bucket.length - 1; index >= 0; index -= 1) {
      const node = bucket[index];
      node.labelY = Math.min(maxY, node.labelY);
      maxY = node.labelY - 34;
    }
  }
}

function renderSwimlaneRow(character) {
  const segments = buildLocationSegments(character.id);
  const events = filteredTimelineItems().filter((item) => eventInvolvesCharacter(item, character.id));
  const currentState = getCharacterStateAt(character.id, state.tick);
  const goals = getGoalsAt(character.id, state.tick);
  return `
    <div class="swimlane__row">
      <div class="swimlane__meta">
        <button data-action="open-character" data-character-id="${escapeHtml(character.id)}">${escapeHtml(character.name)}</button>
        <p>${escapeHtml(currentState.location || "Location unresolved")}</p>
      </div>
      <div class="lane-track">
        ${segments
          .map((segment) => {
            const left = scalePercent(segment.startTick);
            const right = scalePercent(segment.endTick);
            const width = Math.max(4, right - left);
            return `
              <div class="lane-segment" style="left:${left}%; width:${width}%; background:${segment.color}33; border-color:${segment.color}55;">
                <span style="color:${segment.color};">${escapeHtml(segment.location)}</span>
              </div>
            `;
          })
          .join("")}
        ${events
          .map((event) => {
            const left = scalePercent(event.timeline_index);
            const color = markerColor(event);
            return `
              <button
                class="lane-marker ${event.event_kind === "scheduled" ? "lane-marker--scheduled" : ""}"
                style="left:${left}%; background:${event.event_kind === "scheduled" ? "transparent" : color}; border-color:${color};"
                data-action="open-event"
                data-event-id="${escapeHtml(event.event_id)}"
                title="${escapeHtml(eventTooltip(event))}"
              ></button>
            `;
          })
          .join("")}
        <div class="lane-track__cursor" style="left:${scalePercent(state.tick)}%;"></div>
        <div class="lane-state">
          <span><strong>State:</strong> ${escapeHtml(describeVisibleState(currentState))}</span>
          <span><strong>${state.mode === "internal" ? "Goal" : "Beat"}</strong> ${escapeHtml(describeLaneFocus(goals, currentState))}</span>
        </div>
      </div>
    </div>
  `;
}

function renderPanel() {
  if (state.panel?.type === "event") {
    return renderEventPanel(state.panel.eventId);
  }
  if (state.panel?.type === "character") {
    return renderCharacterPanel(state.panel.characterId);
  }
  return renderPanelPlaceholder();
}

function renderPanelPlaceholder() {
  return `
    <div class="panel-header">
      <div>
        <p class="card__kicker">Slide-in panel</p>
        <h2>Keep the world in view</h2>
        <p>Click any event marker or character name to inspect details without losing the shared cursor.</p>
      </div>
    </div>
    <p class="footer-note">
      The current session file already exposes state, goals, relationships, and scheduled events. Scene transcripts are not persisted yet, so detailed beat-by-beat dialogue will appear here once the backend starts storing it.
    </p>
  `;
}

function renderEventPanel(eventId) {
  const event = state.model.timelineItems.find((item) => item.event_id === eventId);
  if (!event) {
    return renderMissingPanel("Event not found", "This marker no longer exists in the session data.");
  }
  const stateDeltas = state.model.stateChanges.filter((entry) => entry.event_id === eventId);
  const relationshipDeltas = state.model.relationships.filter((entry) => entry.event_id === eventId);
  const memories = state.model.memories.filter((memory) => memory.event_id === eventId);
  const participants = resolveParticipants(event.participants);

  return `
    <div class="panel-header">
      <div>
        <p class="card__kicker">${escapeHtml(event.event_kind === "scheduled" ? "Scheduled scene" : "Scene detail")}</p>
        <h2>${escapeHtml(itemLabel(event))}</h2>
        <p>${escapeHtml(formatTimelineMeta(event.timeline_index, event.location || "Unknown location", humanizeSlug(event.seed_type || event.resolution_mode || "scene")))}</p>
      </div>
      <button class="close-button" data-action="close-panel" aria-label="Close panel">×</button>
    </div>

    <div class="stack">
      <section class="detail-item">
        <h4>External view</h4>
        <p class="meta-line">${escapeHtml(event.description || "No scene description was stored for this entry.")}</p>
        ${
          event.outcome_summary
            ? `<p>${escapeHtml(event.outcome_summary)}</p>`
            : `<p>${escapeHtml(event.event_kind === "scheduled" ? "This beat is scheduled ahead of the current cursor, so only the setup exists right now." : "Outcome summary not recorded.")}</p>`
        }
      </section>

      <section class="detail-item">
        <h4>Participants</h4>
        <div class="pill-row">
          ${participants.length
            ? participants
                .map(
                  (participant) => `
                    <span class="pill">
                      <button data-action="open-character" data-character-id="${escapeHtml(participant.id)}">${escapeHtml(participant.name)}</button>
                    </span>
                  `,
                )
                .join("")
            : `<span class="pill">No participant mapping yet</span>`}
        </div>
      </section>

      ${
        state.mode === "internal"
          ? `
            <section class="detail-item">
              <h4>Internal layer</h4>
              <p class="meta-line">
                ${escapeHtml(
                  stateDeltas.length || relationshipDeltas.length || memories.length
                    ? "State shifts, trust changes, and memory echoes linked to this event."
                    : "This session format does not yet store beat-by-beat transcript internals for this scene.",
                )}
              </p>
            </section>
            ${renderDetailList("State deltas", stateDeltas.map(describeStateDelta), "No recorded state deltas for this event.")}
            ${renderDetailList("Relationship shifts", relationshipDeltas.map(describeRelationshipDelta), "No relationship deltas were attached to this event.")}
            ${renderMemoryList(memories)}
          `
          : `
            <p class="footer-note">
              Switch to Internal mode to reveal goal changes, relationship movement, and any memory summaries linked to this scene.
            </p>
          `
      }
    </div>
  `;
}

function renderCharacterPanel(characterId) {
  const character = state.model.characterById[characterId];
  if (!character) {
    return renderMissingPanel("Character not found", "This cast member is not in the current session.");
  }
  const currentState = getCharacterStateAt(characterId, state.tick);
  const goals = getGoalsAt(characterId, state.tick);
  const memories = getMemoriesForCharacter(characterId);
  const relationshipSnapshot = getRelationshipsForCharacter(characterId, state.tick);
  const radar = buildDimensionRadar(character);

  return `
    <div class="panel-header">
      <div>
        <p class="card__kicker">Character deep dive</p>
        <h2>${escapeHtml(character.name)}</h2>
        <p>${escapeHtml(currentState.location || "Location unresolved")} · ${escapeHtml(character.identity.background || "No background note")}</p>
      </div>
      <button class="close-button" data-action="close-panel" aria-label="Close panel">×</button>
    </div>

    <div class="stack">
      <section class="detail-item">
        <h4>Current state at ${escapeHtml(formatTick(state.tick))}</h4>
        <p><strong>Observable:</strong> ${escapeHtml(describeVisibleState(currentState))}</p>
        ${
          state.mode === "internal"
            ? `<p><strong>Active goal:</strong> ${escapeHtml(goals[0]?.goal || "No active goal stored")}</p>`
            : ""
        }
      </section>

      <section class="detail-item">
        <h4>Identity frame</h4>
        <div class="pill-row">
          ${renderIdentityPills(character)}
        </div>
      </section>

      ${
        radar
          ? `
            <section class="detail-item">
              <h4>Dimension radar</h4>
              <div class="radar-shell">${radar}</div>
            </section>
          `
          : ""
      }

      <section class="goal-list">
        <h3>Goal stack</h3>
        ${
          goals.length
            ? goals.map((goal) => renderGoal(goal)).join("")
            : `<div class="goal-item"><p class="meta-line">No goal stack history was available at this cursor.</p></div>`
        }
      </section>

      <section class="detail-list">
        <h3>Relationship snapshot</h3>
        ${
          relationshipSnapshot.length
            ? relationshipSnapshot.map(renderRelationshipItem).join("")
            : `<div class="detail-item"><p class="meta-line">No relationship edges were visible for this character at the current tick.</p></div>`
        }
      </section>

      <section class="memory-list">
        <h3>Memory log</h3>
        ${
          memories.length
            ? memories.map(renderMemoryItem).join("")
            : `<div class="memory-item"><p class="meta-line">No episodic memories have been persisted for this character yet.</p></div>`
        }
      </section>
    </div>
  `;
}

function renderMissingPanel(title, message) {
  return `
    <div class="panel-header">
      <div>
        <p class="card__kicker">Unavailable</p>
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(message)}</p>
      </div>
      <button class="close-button" data-action="close-panel" aria-label="Close panel">×</button>
    </div>
  `;
}

function renderDetailList(title, items, emptyMessage) {
  return `
    <section class="detail-list">
      <h3>${escapeHtml(title)}</h3>
      ${
        items.length
          ? items
              .map(
                (item) => `
                  <div class="detail-item">
                    <p>${escapeHtml(item)}</p>
                  </div>
                `,
              )
              .join("")
          : `<div class="detail-item"><p class="meta-line">${escapeHtml(emptyMessage)}</p></div>`
      }
    </section>
  `;
}

function renderMemoryList(memories) {
  return `
    <section class="memory-list">
      <h3>Memory echoes</h3>
      ${
        memories.length
          ? memories.map(renderMemoryItem).join("")
          : `<div class="memory-item"><p class="meta-line">No memory summaries were attached to this event.</p></div>`
      }
    </section>
  `;
}

function renderMemoryItem(memory) {
  return `
    <div class="memory-item">
      <h4>${escapeHtml(memory.summary || "Untitled memory")}</h4>
      <p class="meta-line">${escapeHtml(formatTick(memory.replay_key.timeline_index))} · salience ${escapeHtml(formatPercent(memory.salience || 0))}</p>
      <p>${escapeHtml(memory.location || "Location not recorded")}</p>
    </div>
  `;
}

function renderGoal(goal) {
  return `
    <div class="goal-item">
      <h4>P${escapeHtml(String(goal.priority || "?"))} · ${escapeHtml(goal.goal || "Untitled goal")}</h4>
      <p class="meta-line">${escapeHtml(humanizeSlug(goal.time_horizon || "unknown horizon"))}</p>
      <p>${escapeHtml(goal.motivation || "No motivation note recorded.")}</p>
      ${
        state.mode === "internal"
          ? `<p><strong>Obstacle:</strong> ${escapeHtml(goal.obstacle || "Unknown")}<br /><strong>Abandon if:</strong> ${escapeHtml(goal.abandon_condition || "Not specified")}</p>`
          : ""
      }
    </div>
  `;
}

function renderRelationshipItem(relationship) {
  const target = state.model.characterById[relationship.to_character_id];
  const name = target?.name || humanizeSlug(relationship.to_character_id);
  return `
    <div class="detail-item">
      <h4>${escapeHtml(name)}</h4>
      <p class="meta-line">Trust ${escapeHtml(formatDecimal(relationship.trust_value || 0))}</p>
      <p>${escapeHtml(relationship.sentiment_shift || relationship.reason || "No sentiment summary")}</p>
      ${state.mode === "internal" && relationship.reason ? `<p>${escapeHtml(relationship.reason)}</p>` : ""}
    </div>
  `;
}

function renderIdentityPills(character) {
  const buckets = [
    ...character.identity.core_traits,
    ...character.identity.values,
    ...character.identity.desires,
  ].filter(Boolean);
  if (!buckets.length) {
    return `<span class="pill">No trait metadata persisted</span>`;
  }
  return buckets
    .slice(0, 8)
    .map((item) => `<span class="pill">${escapeHtml(item)}</span>`)
    .join("");
}

function buildDimensionRadar(character) {
  const initial = {
    ...ensureRecord(character.identity.universal_dimensions),
    ...ensureRecord(character.identity.prominent_dimensions),
  };
  const current = {};
  for (const [key, value] of Object.entries(initial)) {
    current[key] = Number(value || 0);
  }
  const labels = Object.keys(current).slice(0, 6);
  if (!labels.length) {
    return "";
  }
  const size = 280;
  const center = size / 2;
  const radius = 92;
  const levels = [0.25, 0.5, 0.75, 1];
  const makePoint = (index, total, scale) => {
    const angle = (-Math.PI / 2) + (index / total) * Math.PI * 2;
    return {
      x: center + Math.cos(angle) * radius * scale,
      y: center + Math.sin(angle) * radius * scale,
    };
  };
  const polygonFor = (values) =>
    labels
      .map((label, index) => {
        const raw = Number(values[label] || 0);
        const normalized = raw > 1 ? Math.min(raw / 100, 1) : Math.max(0, Math.min(raw, 1));
        const point = makePoint(index, labels.length, normalized);
        return `${point.x},${point.y}`;
      })
      .join(" ");
  return `
    <svg viewBox="0 0 ${size} ${size}" role="img" aria-label="Dimension radar">
      ${levels
        .map((level) => {
          const points = labels.map((_, index) => {
            const point = makePoint(index, labels.length, level);
            return `${point.x},${point.y}`;
          });
          return `<polygon points="${points.join(" ")}" fill="none" stroke="rgba(24,33,45,0.08)" />`;
        })
        .join("")}
      ${labels
        .map((label, index) => {
          const point = makePoint(index, labels.length, 1);
          return `
            <line x1="${center}" y1="${center}" x2="${point.x}" y2="${point.y}" stroke="rgba(24,33,45,0.08)" />
            <text x="${point.x}" y="${point.y}" font-size="11" fill="rgba(24,33,45,0.64)" text-anchor="middle" dominant-baseline="middle">
              ${escapeHtml(truncate(humanizeSlug(label), 12))}
            </text>
          `;
        })
        .join("")}
      <polygon points="${polygonFor(initial)}" fill="rgba(35,65,93,0.14)" stroke="${EVENT_COLORS.solo}" stroke-width="2" />
      <polygon points="${polygonFor(current)}" fill="rgba(173,79,45,0.16)" stroke="${EVENT_COLORS.goal_collision}" stroke-width="2" />
    </svg>
  `;
}

function bindEvents() {
  root.querySelectorAll("[data-action]").forEach((element) => {
    element.addEventListener("click", handleAction);
  });
  const scrubber = root.querySelector('input[data-action="scrub"]');
  if (scrubber) {
    scrubber.addEventListener("input", (event) => {
      setTick(Number(event.target.value));
    });
  }
  const speedSelect = root.querySelector('select[data-action="speed-select"]');
  if (speedSelect) {
    speedSelect.addEventListener("change", (event) => {
      state.playSpeed = Number(event.target.value || 1);
      restartPlaybackIfNeeded();
    });
  }
}

function handleAction(event) {
  const button = event.currentTarget;
  const action = button.dataset.action;
  if (!action) {
    return;
  }
  if (action === "play-toggle") {
    togglePlayback();
  } else if (action === "reset-cursor") {
    setTick(state.model.minTick);
  } else if (action === "jump-now") {
    setTick(state.model.currentTick);
  } else if (action === "mode") {
    state.mode = button.dataset.mode || "external";
    render();
  } else if (action === "toggle-character") {
    toggleCharacter(button.dataset.characterId);
  } else if (action === "show-all") {
    state.visibleCharacterIds = new Set(state.model.characters.map((character) => character.id));
    render();
  } else if (action === "toggle-diagnostics") {
    state.showDiagnostics = !state.showDiagnostics;
    render();
  } else if (action === "open-event") {
    state.panel = { type: "event", eventId: button.dataset.eventId };
    render();
  } else if (action === "open-character") {
    state.panel = { type: "character", characterId: button.dataset.characterId };
    render();
  } else if (action === "close-panel") {
    state.panel = null;
    render();
  }
}

function toggleCharacter(characterId) {
  if (!characterId) {
    return;
  }
  if (state.visibleCharacterIds.has(characterId) && state.visibleCharacterIds.size > 1) {
    state.visibleCharacterIds.delete(characterId);
  } else {
    state.visibleCharacterIds.add(characterId);
  }
  render();
}

function togglePlayback() {
  state.isPlaying = !state.isPlaying;
  if (state.isPlaying) {
    startPlayback();
  } else {
    stopPlayback();
    render();
  }
}

function startPlayback() {
  stopPlayback();
  state.playbackHandle = window.setInterval(() => {
    const next = Math.min(state.tick + state.playSpeed, state.model.maxTick);
    setTick(next, { rerender: false });
    if (next >= state.model.maxTick) {
      state.isPlaying = false;
      stopPlayback();
    }
    render();
  }, 380);
}

function stopPlayback() {
  if (state.playbackHandle) {
    window.clearInterval(state.playbackHandle);
    state.playbackHandle = null;
  }
}

function restartPlaybackIfNeeded() {
  if (state.isPlaying) {
    startPlayback();
  }
}

function setTick(nextTick, options = {}) {
  state.tick = clamp(Math.round(nextTick), state.model.minTick, state.model.maxTick);
  if (options.rerender !== false) {
    render();
  }
}

function getVisibleCharacters() {
  return state.model.characters.filter((character) => state.visibleCharacterIds.has(character.id));
}

function filteredTimelineItems() {
  return state.model.timelineItems.filter((item) => {
    if (!state.visibleCharacterIds.size) {
      return true;
    }
    if (!item.participants.length) {
      return true;
    }
    return item.participants.some((participant) => {
      const resolved = resolveCharacterId(participant);
      return resolved ? state.visibleCharacterIds.has(resolved) : false;
    });
  });
}

function countFutureEvents() {
  return state.model.timelineItems.filter((item) => item.timeline_index > state.tick).length;
}

function summarizeLlmIssues(tick) {
  const allIssues = Array.isArray(state.model.llmIssues) ? state.model.llmIssues : [];
  const visibleIssues = allIssues.filter((issue) => issue.timeline_index <= tick);
  const currentTickIssues = visibleIssues.filter((issue) => issue.timeline_index === tick);
  return {
    totalCount: allIssues.length,
    visibleCount: visibleIssues.length,
    currentTickCount: currentTickIssues.length,
    visibleIssues,
  };
}

function getUpcomingItems(limit) {
  return state.model.timelineItems
    .filter((item) => item.timeline_index > state.tick)
    .slice(0, limit);
}

function getMostRecentLoggedItem() {
  return [...state.model.loggedEvents]
    .filter((item) => item.timeline_index <= state.tick)
    .sort((left, right) => right.timeline_index - left.timeline_index)[0] || null;
}

function getCharacterStateAt(characterId, tick) {
  const character = state.model.characterById[characterId];
  const baseState = ensureRecord(character?.snapshot?.current_state);
  const stateEntries = state.model.stateChanges.filter((entry) => entry.character_id === characterId && entry.replay_key.timeline_index <= tick);
  const nextState = { ...baseState };
  for (const entry of stateEntries) {
    nextState[entry.dimension] = entry.to_value;
  }
  return nextState;
}

function getGoalsAt(characterId, tick) {
  const entries = state.model.goalStacks.filter((entry) => entry.character_id === characterId && entry.replay_key.timeline_index <= tick);
  const latest = entries.at(-1);
  if (latest) {
    return latest.goals;
  }
  return state.model.characterById[characterId]?.snapshot?.goals || [];
}

function getMemoriesForCharacter(characterId) {
  return state.model.memories
    .filter((memory) => memory.character_id === characterId && memory.replay_key.timeline_index <= state.tick)
    .sort((left, right) => (Number(right.salience || 0) - Number(left.salience || 0)) || compareReplayItems(right, left))
    .slice(0, 6);
}

function getRelationshipsAt(tick) {
  const latest = new Map();
  for (const relationship of state.model.relationships) {
    if (relationship.replay_key.timeline_index > tick) {
      continue;
    }
    const key = `${relationship.from_character_id}::${relationship.to_character_id}`;
    latest.set(key, relationship);
  }
  return [...latest.values()];
}

function getRelationshipsForCharacter(characterId, tick) {
  return getRelationshipsAt(tick)
    .filter((relationship) => relationship.from_character_id === characterId)
    .sort((left, right) => (right.trust_value || 0) - (left.trust_value || 0));
}

function getNarrativeAt(tick) {
  const snapshots = state.model.snapshots.filter((snapshot) => snapshot.replay_key.timeline_index <= tick);
  const latest = snapshots.at(-1);
  if (latest?.narrative_arc) {
    return latest.narrative_arc;
  }
  return {
    current_phase: state.model.initialArc.current_phase || "setup",
    tension_level: Number(state.model.initialArc.tension_level || 0),
    unresolved_threads: state.model.initialArc.unresolved_threads || [],
    approaching_climax: Boolean(state.model.initialArc.approaching_climax),
  };
}

function buildTensionSeries() {
  const snapshots = state.model.snapshots.map((snapshot) => ({
    tick: snapshot.replay_key.timeline_index,
    tension: Number(snapshot.narrative_arc?.tension_level || 0),
    phase: snapshot.narrative_arc?.current_phase || "setup",
  }));
  if (!snapshots.length) {
    const phase = state.model.initialArc.current_phase || state.model.session.arc_state?.current_phase || "setup";
    const tension = Number(state.model.initialArc.tension_level ?? state.model.session.arc_state?.tension_level ?? 0);
    return [{ tick: state.model.currentTick, tension, phase }];
  }
  if (snapshots.at(-1)?.tick !== state.model.currentTick) {
    const narrative = state.model.session.arc_state || {};
    snapshots.push({
      tick: state.model.currentTick,
      tension: Number(narrative.tension_level || snapshots.at(-1)?.tension || 0),
      phase: narrative.current_phase || snapshots.at(-1)?.phase || "setup",
    });
  }
  return snapshots;
}

function buildLocationSegments(characterId) {
  const entries = state.model.stateChanges
    .filter((entry) => entry.character_id === characterId && entry.dimension === "location")
    .sort(compareReplayItems);
  if (!entries.length) {
    const fallback = getCharacterStateAt(characterId, state.tick).location || "Unplaced";
    return [
      {
        location: fallback,
        startTick: state.model.minTick,
        endTick: state.model.maxTick,
        color: state.model.locationPalette[fallback] || "#537188",
      },
    ];
  }
  return entries.map((entry, index) => {
    const next = entries[index + 1];
    const location = entry.to_value || "Unknown";
    return {
      location,
      startTick: entry.replay_key.timeline_index,
      endTick: next ? next.replay_key.timeline_index : state.model.maxTick,
      color: state.model.locationPalette[location] || LOCATION_COLORS[index % LOCATION_COLORS.length],
    };
  });
}

function eventInvolvesCharacter(event, characterId) {
  return event.participants.some((participant) => resolveCharacterId(participant) === characterId);
}

function resolveCharacterId(ref) {
  return state.model.refMap.get(normalizeRef(ref)) || null;
}

function resolveParticipants(participants) {
  return participants
    .map((participant) => {
      const id = resolveCharacterId(participant);
      if (!id) {
        return null;
      }
      const character = state.model.characterById[id];
      return {
        id,
        name: character?.name || humanizeSlug(id),
      };
    })
    .filter(Boolean);
}

function describeVisibleState(currentState) {
  const fragments = [];
  if (currentState.location) {
    fragments.push(`at ${currentState.location}`);
  }
  if (currentState.current_activity) {
    fragments.push(currentState.current_activity);
  } else if (currentState.physical_state) {
    fragments.push(currentState.physical_state);
  } else if (currentState.emotional_state) {
    fragments.push(currentState.emotional_state);
  }
  return fragments.join(" · ") || "No visible state stored";
}

function describeLaneFocus(goals, currentState) {
  if (state.mode === "internal") {
    return goals[0]?.goal || currentState.emotional_state || currentState.physical_state || "Awaiting inner state";
  }
  return currentState.current_activity || currentState.location || "Waiting";
}

function describeRelationshipState(visibleCharacters) {
  const visibleIds = new Set(visibleCharacters.map((character) => character.id));
  const edges = getRelationshipsAt(state.tick).filter((edge) => visibleIds.has(edge.from_character_id) && visibleIds.has(edge.to_character_id));
  if (!edges.length) {
    return "No directed relationships between the visible agents have been recorded at this cursor.";
  }
  const strongest = [...edges].sort((left, right) => relationshipStrength(right) - relationshipStrength(left))[0];
  const from = state.model.characterById[strongest.from_character_id]?.name || humanizeSlug(strongest.from_character_id);
  const to = state.model.characterById[strongest.to_character_id]?.name || humanizeSlug(strongest.to_character_id);
  return `${from} → ${to} is currently the clearest visible tie, reading as ${humanizeSlug(strongest.sentiment_shift || "neutral")}.`;
}

function describeStateDelta(entry) {
  return `${humanizeSlug(entry.character_id)} · ${humanizeSlug(entry.dimension)} → ${stringifyValue(entry.to_value)}`;
}

function describeRelationshipDelta(entry) {
  return `${humanizeSlug(entry.from_character_id)} → ${humanizeSlug(entry.to_character_id)} · trust ${formatSignedDecimal(entry.trust_delta || 0)} · ${entry.sentiment_shift || "no sentiment label"}`;
}

function buildRelationshipTooltip(edge) {
  const from = state.model.characterById[edge.from_character_id]?.name || humanizeSlug(edge.from_character_id);
  const to = state.model.characterById[edge.to_character_id]?.name || humanizeSlug(edge.to_character_id);
  return `${from} → ${to} · trust ${formatSignedDecimal(edge.trust_value || 0)} · ${humanizeSlug(edge.sentiment_shift || "neutral")}`;
}

function buildCharacterTooltip(characterId) {
  const currentState = getCharacterStateAt(characterId, state.tick);
  return `${state.model.characterById[characterId]?.name || characterId} · ${describeVisibleState(currentState)}`;
}

function buildAtlasSubtitle() {
  const atlas = state.model.storageAtlas;
  return `The loaded checkpoint currently contains ${formatCount(atlas.liveAgentCount)} live agents, ${formatCount(atlas.totalLogEntries)} append-only rows, and an optional ${atlas.sqlTables.length}-table SQL mirror.`;
}

function buildPageHref(mode) {
  const target = mode === "atlas" ? "./atlas.html" : "./index.html";
  const query = params.toString();
  return query ? `${target}?${query}` : target;
}

function buildSubtitle(narrative) {
  const threadCount = Array.isArray(narrative.unresolved_threads) ? narrative.unresolved_threads.length : 0;
  const sourceLabel = state.model.metadata.story_context || basenameStem(state.model.sourcePath) || "simulation";
  return `Phase ${humanizeSlug(narrative.current_phase || "setup")} · ${threadCount} unresolved threads · ${humanizeSlug(sourceLabel)}`;
}

function buildHeroSummary(narrative, nextBeat) {
  const currentBeat = getMostRecentLoggedItem();
  const tensionLine = state.model.metadata.central_tension || "The current session has not stored a central tension note yet.";
  if (currentBeat && nextBeat) {
    return `${tensionLine} Most recently, ${itemLabel(currentBeat)} landed at ${formatTick(currentBeat.timeline_index)}. Next on deck: ${itemLabel(nextBeat)}.`;
  }
  if (nextBeat) {
    return `${tensionLine} The simulation is still staged in opening position, with ${itemLabel(nextBeat)} queued as the next visible beat.`;
  }
  return `${tensionLine} The current cursor is at the edge of recorded story time.`;
}

function buildRunwaySummary(nextBeat) {
  if (!nextBeat) {
    return "The dashboard has caught up with the current story horizon.";
  }
  return `The next visible shift is ${itemLabel(nextBeat)} at ${formatTick(nextBeat.timeline_index)}.`;
}

function buildModeSupportLine() {
  const note = state.model.metadata.writing_style_note || "";
  if (state.mode === "external") {
    return note ? `Writing texture: ${truncate(note, 120)}` : "External mode stays anchored to observable story motion.";
  }
  return "Internal mode highlights goals, emotional state, and inferred relationship pressure where the data exists.";
}

function buildLlmWarningSummary(summary) {
  if (!summary.visibleCount) {
    return `This session has ${summary.totalCount} recorded LLM warnings, but they happen later than the current cursor.`;
  }
  if (summary.currentTickCount > 0) {
    return `This step produced ${summary.currentTickCount} warning${summary.currentTickCount === 1 ? "" : "s"}. The list below keeps the most recent flawed answers visible for inspection.`;
  }
  return `${summary.visibleCount} warning${summary.visibleCount === 1 ? "" : "s"} have happened up to this cursor. The most recent ones stay visible here so pacing and language drift are traceable.`;
}

function buildCollapsedLlmMessage(summary) {
  if (!summary.visibleCount) {
    return `Warnings exist later in the run, but none are active at this cursor. Expand this card only when you want to inspect model failures.`;
  }
  return `${summary.visibleCount} warning${summary.visibleCount === 1 ? "" : "s"} are visible at this cursor. Expand this card to inspect the latest structured-output failures.`;
}

function buildLocationSummary(characterId) {
  return getCharacterStateAt(characterId, state.tick).location || "Unplaced";
}

function countCharacterEvents(characterId) {
  return state.model.timelineItems.filter((item) => eventInvolvesCharacter(item, characterId)).length;
}

function relationshipStrength(edge) {
  const trust = Math.abs(Number(edge?.trust_value || 0));
  const sentimentBonus = edge?.sentiment_shift && edge.sentiment_shift !== "neutral" ? 0.08 : 0;
  return trust + sentimentBonus;
}

function emotionColorForCharacter(characterId, tick) {
  const currentState = getCharacterStateAt(characterId, tick);
  const value = `${currentState.emotional_state || ""} ${currentState.physical_state || ""}`.toLowerCase();
  if (/(grief|grieving|despair|fear|hostile|wounded|burdened)/.test(value)) {
    return "#8c2f2a";
  }
  if (/(calm|focused|strategic|calculating|purposeful)/.test(value)) {
    return "#23415d";
  }
  if (/(victorious|loyal|hope|resolved)/.test(value)) {
    return "#4f7a51";
  }
  return "#7d7662";
}

function relationshipColor(sentiment, trustValue) {
  const mood = (sentiment || "").toLowerCase();
  if (/(hostile|enmity|critical|grieving|conflict|betray)/.test(mood)) {
    return "#8c2f2a";
  }
  if (/(loyal|trust|respect|allied|positive|gratitude)/.test(mood)) {
    return "#b0642b";
  }
  return Number(trustValue || 0) > 0.5 ? "#23415d" : "#5f6b7a";
}

function itemLabel(item) {
  if (item.event_kind === "scheduled") {
    return item.event_id || "Scheduled beat";
  }
  if (item.description) {
    return item.description;
  }
  return item.event_id || "Scene";
}

function eventTooltip(item) {
  const participants = resolveParticipants(item.participants).map((participant) => participant.name).join(", ");
  return [
    formatTick(item.timeline_index),
    item.location || "Unknown location",
    participants || "No mapped participants",
    item.outcome_summary || item.description || "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function markerColor(item) {
  return EVENT_COLORS[item.seed_type] || EVENT_COLORS[item.resolution_mode] || EVENT_COLORS.world;
}

function markerSize(item) {
  if (item.event_kind === "scheduled") {
    return 8;
  }
  return 6 + Math.round((Number(item.salience || 0) * 10) / 2);
}

function humanizePromptName(value) {
  const cleaned = String(value || "")
    .replace(/^p\d+_\d+_/, "")
    .replace(/^p\d+_/, "");
  return humanizeSlug(cleaned || "prompt");
}

function scaleTick(tick, width, left, right) {
  const min = state.model.minTick;
  const max = Math.max(state.model.maxTick, min + 1);
  const normalized = (tick - min) / (max - min);
  return left + normalized * (width - left - right);
}

function scalePercent(tick) {
  const min = state.model.minTick;
  const max = Math.max(state.model.maxTick, min + 1);
  return ((tick - min) / (max - min)) * 100;
}

function pickAxisTicks(min, max, desiredCount) {
  if (min === max) {
    return [min];
  }
  const steps = [];
  const count = Math.max(2, desiredCount);
  for (let index = 0; index < count; index += 1) {
    const ratio = index / (count - 1);
    steps.push(Math.round(min + ratio * (max - min)));
  }
  return [...new Set(steps)];
}

function formatTick(tick) {
  return formatStoryTime(tick);
}

function formatTickDuration(minutes) {
  const numeric = Number(minutes || 0);
  if (!numeric) {
    return "";
  }
  if (numeric < 60) {
    return `${numeric} min`;
  }
  if (numeric >= 1440) {
    const days = Math.floor(numeric / 1440);
    const remainder = numeric % 1440;
    if (remainder === 0) {
      return `${days} day${days === 1 ? "" : "s"}`;
    }
    const hours = Math.round(remainder / 60);
    return `${days}d ${hours}h`;
  }
  const hours = numeric / 60;
  if (Number.isInteger(hours)) {
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  return `${hours.toFixed(1)} hours`;
}

function formatStoryTime(minutes) {
  const numeric = Math.max(0, Number(minutes || 0));
  if (!numeric) {
    return "start";
  }
  return `+${formatTickDuration(numeric)}`;
}

function getTickDurationMinutes(tick, model) {
  const value = Number(model?.tickDurationByTick?.[tick] || 0);
  return value > 0 ? value : null;
}

function formatTickScale(tick, model) {
  const minutes = getTickDurationMinutes(tick, model);
  if (!minutes) {
    return "";
  }
  return `+${formatTickDuration(minutes)}`;
}

function formatTimelineMeta(tick, ...parts) {
  const items = [`Story ${formatTick(tick)}`];
  const scale = formatTickScale(tick, state.model);
  if (scale) {
    items.push(scale);
  }
  for (const part of parts) {
    if (part) {
      items.push(String(part));
    }
  }
  return items.join(" · ");
}

function formatTickLabel(tick, model) {
  const scale = formatTickScale(tick, model);
  const snapshot = model.snapshots.find((entry) => entry.replay_key.timeline_index === tick);
  if (snapshot) {
    return [snapshot.replay_key.tick, `Story ${formatTick(tick)}`, formatStepAtTick(tick, model), scale].filter(Boolean).join(" · ");
  }
  if (tick === model.currentTick) {
    return [model.currentTickLabel, `Story ${formatTick(tick)}`, formatCurrentStep(tick, model), scale].filter(Boolean).join(" · ");
  }
  return [`Story ${formatTick(tick)}`, formatStepAtTick(tick, model), scale].filter(Boolean).join(" · ");
}

function formatCurrentStep(tick, model) {
  if (tick !== model.currentTick) {
    return formatStepAtTick(tick, model);
  }
  const current = Number(model?.metadata?.tick_count || 0);
  return current > 0 ? `Step ${current}` : "";
}

function formatStepAtTick(tick, model) {
  const snapshots = Array.isArray(model?.snapshots) ? model.snapshots : [];
  const index = snapshots.findIndex((entry) => Number(entry.replay_key.timeline_index) === Number(tick));
  if (index >= 0) {
    return `Step ${index + 1}`;
  }
  return "";
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function formatDecimal(value) {
  return Number(value || 0).toFixed(2);
}

function formatSignedDecimal(value) {
  const numeric = Number(value || 0);
  return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(2)}`;
}

function humanizeSlug(value) {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function normalizeParticipants(participants) {
  if (!Array.isArray(participants)) {
    return [];
  }
  return participants.map((participant) => String(participant));
}

function groupBy(items, key) {
  return items.reduce((groups, item) => {
    const value = item?.[key] || "Other";
    if (!groups[value]) {
      groups[value] = [];
    }
    groups[value].push(item);
    return groups;
  }, {});
}

function normalizeTextList(value) {
  if (!Array.isArray(value)) {
    if (!value) {
      return [];
    }
    return String(value)
      .split(/[;,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (value.length > 8 && value.every((item) => typeof item === "string" && item.length <= 1)) {
    return value
      .join("")
      .split(/[;,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return value
    .map((item) => String(item).trim())
    .filter(Boolean);
}

function ensureRecord(value) {
  return value && typeof value === "object" ? value : {};
}

function normalizeRef(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
}

function basenameStem(path) {
  const parts = String(path || "").split("/");
  const last = parts.at(-1) || "";
  return last.replace(/\.[a-z0-9]+$/i, "");
}

function truncate(value, length) {
  const text = String(value || "");
  if (text.length <= length) {
    return text;
  }
  return `${text.slice(0, Math.max(0, length - 1))}…`;
}

function stringifyValue(value) {
  if (value == null) {
    return "null";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!bytes) {
    return "0 B";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 ** 2) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  if (bytes < 1024 ** 3) {
    return `${(bytes / (1024 ** 2)).toFixed(2)} MB`;
  }
  return `${(bytes / (1024 ** 3)).toFixed(2)} GB`;
}

function pluralize(word, count) {
  return Number(count || 0) === 1 ? word : `${word}s`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function debounce(callback, waitMs) {
  let handle = null;
  return (...args) => {
    if (handle) {
      window.clearTimeout(handle);
    }
    handle = window.setTimeout(() => callback(...args), waitMs);
  };
}

function installTestingHooks() {
  window.render_game_to_text = () => {
    if (!state.model) {
      return JSON.stringify({ status: "loading" }, null, 2);
    }
    const visibleCharacters = getVisibleCharacters().map((character) => ({
      id: character.id,
      name: character.name,
      location: getCharacterStateAt(character.id, state.tick).location || "",
      top_goal: getGoalsAt(character.id, state.tick)[0]?.goal || "",
    }));
    const panel =
      state.panel?.type === "event"
        ? { type: "event", id: state.panel.eventId }
        : state.panel?.type === "character"
          ? { type: "character", id: state.panel.characterId }
          : null;
    return JSON.stringify(
      {
        mode: state.mode,
        tick: state.tick,
        max_tick: state.model.maxTick,
        storage: {
          top_level_fields: state.model.storageAtlas.sessionShape.length,
          append_rows: state.model.storageAtlas.totalLogEntries,
          sql_tables: state.model.storageAtlas.sqlTables.length,
        },
        visible_characters: visibleCharacters,
        logged_events: state.model.loggedEvents.length,
        scheduled_events: state.model.scheduledEvents.length,
        llm_warnings_visible: summarizeLlmIssues(state.tick).visibleCount,
        llm_warnings_total: summarizeLlmIssues(state.tick).totalCount,
        panel,
        note: "Origin is the current simulation timeline. Higher tick values move forward in story time.",
      },
      null,
      2,
    );
  };

  window.advanceTime = async (ms) => {
    if (!state.model) {
      return;
    }
    const increment = Math.max(1, Math.round(ms / 120));
    setTick(Math.min(state.model.maxTick, state.tick + increment), { rerender: false });
    render();
  };
}

function renderError(error) {
  root.className = "app-shell app-shell--error";
  root.innerHTML = `
    <div class="error-state">
      <p class="eyebrow">${escapeHtml(PAGE_MODE === "atlas" ? "Dreamdive Data Atlas" : "Visualization Layer")}</p>
      <h1>Unable to load the simulation session</h1>
      <p>${escapeHtml(error.message || "Unknown error")}</p>
      <p class="footer-note">
        The default page expects a session file at <code>${escapeHtml(DEFAULT_SESSION_PATH)}</code>.
        You can override it with a <code>?session=...</code> query parameter.
      </p>
    </div>
  `;
}

import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import ELK from "elkjs/lib/elk.bundled.js";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./styles.css";

const elk = new ELK();
const ENTITY_WIDTH = 236;
const ENTITY_HEIGHT = 78;
const STAGE_HEADER = 72;
const STAGE_GAP = 56;
const STATUS_TONES = {
  passed: "success",
  pass: "success",
  selected: "success",
  complete: "success",
  running: "active",
  awaiting_critic: "active",
  human_gate: "warning",
  warning: "warning",
  required: "warning",
  blocked: "danger",
  failed: "danger",
  fail: "danger",
  needs_repair: "danger",
  pending: "muted",
};

const statusTone = (status) => STATUS_TONES[String(status || "").toLowerCase()] || "muted";
const encodePath = (path) => String(path || "").split("/").map(encodeURIComponent).join("/");
const mediaUrl = (path) => `/media/${encodePath(path)}`;
const prettyBytes = (bytes) => {
  if (!Number.isFinite(bytes)) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

const StageNode = memo(({ data }) => (
  <div className={`stage-frame tone-${statusTone(data.stage.status)}`}>
    <div className="stage-frame-heading">
      <span>{data.stage.id}</span>
      <strong>{data.stage.title}</strong>
      <em>{data.stage.node_count} nodes</em>
    </div>
    <p>{data.stage.question}</p>
  </div>
));

const EntityNode = memo(({ data, selected }) => {
  const hasMedia = data.files?.some((file) => ["image", "video", "audio"].includes(file.kind));
  const hasPrompt = Boolean(data.prompts?.length);
  return (
    <div className={`entity-node tone-${statusTone(data.status)} ${data.dimmed ? "is-dimmed" : ""} ${selected ? "is-selected" : ""}`}>
      <Handle id="in" type="target" position={Position.Left} />
      <Handle id="up" type="target" position={Position.Top} />
      <div className="entity-node-topline">
        <span>{data.kind.replaceAll("-", " ")}</span>
        <i>{data.status}</i>
      </div>
      <strong>{data.title}</strong>
      <p>{data.subtitle || data.id}</p>
      <div className="entity-node-marks" aria-label="available details">
        {hasPrompt && <span>P {data.prompts.length}</span>}
        {hasMedia && <span>M {data.files.filter((file) => ["image", "video", "audio"].includes(file.kind)).length}</span>}
        {data.attempts?.length > 0 && <span>R {data.attempts.length}</span>}
      </div>
      <Handle id="out" type="source" position={Position.Right} />
      <Handle id="down" type="source" position={Position.Bottom} />
    </div>
  );
});

const nodeTypes = { stageGroup: StageNode, entity: EntityNode };

async function layoutSnapshot(snapshot) {
  const childrenByStage = new Map(snapshot.stages.map((stage) => [stage.id, []]));
  snapshot.nodes.forEach((node) => childrenByStage.get(node.stage_id)?.push(node));
  const stageLayouts = [];

  for (const stage of snapshot.stages) {
    const stageNodes = childrenByStage.get(stage.id) || [];
    const ids = new Set(stageNodes.map((node) => node.id));
    const internalEdges = snapshot.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
    const graph = {
      id: stage.id,
      layoutOptions: {
        "elk.algorithm": "layered",
        "elk.direction": "DOWN",
        "elk.edgeRouting": "ORTHOGONAL",
        "elk.spacing.nodeNode": "24",
        "elk.layered.spacing.nodeNodeBetweenLayers": "48",
        "elk.padding": `[top=${STAGE_HEADER + 18},left=22,bottom=28,right=22]`,
        "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
      },
      children: stageNodes.map((node) => ({ id: node.id, width: ENTITY_WIDTH, height: ENTITY_HEIGHT })),
      edges: internalEdges.map((edge) => ({ id: edge.id, sources: [edge.source], targets: [edge.target] })),
    };
    const layout = await elk.layout(graph);
    const width = Math.max(320, Number(layout.width || 0));
    const height = Math.max(300, Number(layout.height || 0));
    stageLayouts.push({ stage, stageNodes, layout, width, height });
  }

  const maxHeight = Math.max(...stageLayouts.map((item) => item.height), 340);
  let cursorX = 0;
  const flowNodes = [];
  for (const item of stageLayouts) {
    const groupId = `stage-group:${item.stage.id}`;
    const groupWidth = item.width;
    flowNodes.push({
      id: groupId,
      type: "stageGroup",
      position: { x: cursorX, y: 0 },
      data: { stage: item.stage },
      draggable: false,
      selectable: true,
      focusable: true,
      style: { width: groupWidth, height: maxHeight },
      zIndex: -1,
    });
    const positions = new Map((item.layout.children || []).map((node) => [node.id, node]));
    for (const entity of item.stageNodes) {
      const placed = positions.get(entity.id) || { x: 24, y: STAGE_HEADER + 24 };
      flowNodes.push({
        id: entity.id,
        type: "entity",
        parentId: groupId,
        extent: "parent",
        position: { x: Number(placed.x || 0), y: Number(placed.y || STAGE_HEADER + 20) },
        data: entity,
        draggable: false,
        connectable: false,
        selectable: true,
        focusable: true,
        style: { width: ENTITY_WIDTH, height: ENTITY_HEIGHT },
      });
    }
    cursorX += groupWidth + STAGE_GAP;
  }

  const stageByNode = new Map(snapshot.nodes.map((node) => [node.id, node.stage_id]));
  const flowEdges = snapshot.edges.map((edge) => {
    const sameStage = stageByNode.get(edge.source) === stageByNode.get(edge.target);
    const isWarning = edge.kind === "unresolved";
    const isReceipt = edge.kind === "input-receipt" || edge.kind === "receipt";
    return {
      ...edge,
      type: "smoothstep",
      sourceHandle: sameStage ? "down" : "out",
      targetHandle: sameStage ? "up" : "in",
      markerEnd: { type: MarkerType.ArrowClosed, width: 13, height: 13 },
      style: {
        stroke: isWarning ? "var(--observer-warning)" : isReceipt ? "var(--observer-receipt)" : "var(--observer-edge)",
        strokeWidth: edge.kind === "input" || edge.kind === "media-input" ? 2 : 1.35,
        strokeDasharray: isReceipt ? "5 4" : undefined,
      },
      data: edge,
      animated: false,
    };
  });
  return { nodes: flowNodes, edges: flowEdges };
}

function JsonTree({ value, depth = 0, name = null }) {
  if (value === null || typeof value !== "object") {
    return <div className="json-leaf"><span>{name}</span><code>{JSON.stringify(value)}</code></div>;
  }
  const entries = Array.isArray(value) ? value.map((item, index) => [String(index), item]) : Object.entries(value);
  if (!entries.length) return <div className="json-leaf"><span>{name}</span><code>{Array.isArray(value) ? "[]" : "{}"}</code></div>;
  return (
    <details className="json-branch" open={depth < 2}>
      <summary>{name ?? (Array.isArray(value) ? `Array(${value.length})` : "Object")}</summary>
      <div>{entries.map(([key, item]) => <JsonTree key={key} value={item} depth={depth + 1} name={key} />)}</div>
    </details>
  );
}

function MediaPreview({ file }) {
  if (!file?.exists) return <div className="missing-media">파일 없음 · {file?.path}</div>;
  if (file.kind === "image") return <img src={mediaUrl(file.path)} loading="lazy" alt={file.name || file.path} />;
  if (file.kind === "video") return <video src={mediaUrl(file.path)} controls preload="metadata" />;
  if (file.kind === "audio") return <audio src={mediaUrl(file.path)} controls preload="metadata" />;
  return null;
}

function AttemptHistory({ attempts }) {
  const [selected, setSelected] = useState(attempts.at(-1)?.id);
  useEffect(() => setSelected(attempts.at(-1)?.id), [attempts]);
  if (!attempts.length) return <p className="empty-state">이 노드에 기록된 재시도 이력이 없습니다.</p>;
  const current = attempts.find((attempt) => attempt.id === selected) || attempts.at(-1);
  return (
    <div className="attempt-history">
      <div className="attempt-list">
        {attempts.map((attempt) => (
          <button key={attempt.id} className={attempt.id === current.id ? "active" : ""} onClick={() => setSelected(attempt.id)}>
            <strong>{attempt.id}</strong><span>{attempt.selected ? "selected" : attempt.decision || "attempt"}</span>
          </button>
        ))}
      </div>
      <div className="attempt-detail">
        <dl><dt>전략</dt><dd>{current.variation_strategy || "—"}</dd><dt>판정</dt><dd>{current.decision || "—"}</dd></dl>
        {current.prompt && <pre>{current.prompt}</pre>}
        {current.candidate && <div className="media-tile"><MediaPreview file={current.candidate} /><p>{current.candidate.path}</p></div>}
        {current.review && <JsonTree value={current.review} name="review" />}
      </div>
    </div>
  );
}

function Inspector({ node, edges, onClose, onNavigate }) {
  const [tab, setTab] = useState("overview");
  useEffect(() => setTab("overview"), [node?.id]);
  if (!node) return null;
  const media = (node.files || []).filter((file) => ["image", "video", "audio"].includes(file.kind));
  const incoming = edges.filter((edge) => edge.target === node.id);
  const outgoing = edges.filter((edge) => edge.source === node.id);
  const tabs = [
    ["overview", "개요"], ["structured", "구조화"], ["prompts", `프롬프트 ${node.prompts?.length || ""}`],
    ["media", `미디어 ${media.length || ""}`], ["attempts", `재시도 ${node.attempts?.length || ""}`], ["files", `파일 ${node.files?.length || ""}`],
  ];
  return (
    <aside className="inspector" aria-label="선택한 노드 상세">
      <header>
        <div><span>{node.stage_id} · {node.kind}</span><h2>{node.title}</h2><p>{node.subtitle}</p></div>
        <button onClick={onClose} aria-label="상세 닫기">×</button>
      </header>
      <nav>{tabs.map(([id, label]) => <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{label}</button>)}</nav>
      <div className="inspector-body">
        {tab === "overview" && <>
          <dl className="fact-list"><dt>상태</dt><dd>{node.status}</dd><dt>노드 ID</dt><dd>{node.id}</dd><dt>직접 입력</dt><dd>{incoming.length}</dd><dt>직접 출력</dt><dd>{outgoing.length}</dd></dl>
          <section><h3>직접 입력</h3>{incoming.length ? incoming.map((edge) => <button className="lineage-row" key={edge.id} onClick={() => onNavigate(edge.source)}><span>{edge.label}</span><code>{edge.source}</code></button>) : <p className="empty-state">없음</p>}</section>
          <section><h3>직접 출력</h3>{outgoing.length ? outgoing.map((edge) => <button className="lineage-row" key={edge.id} onClick={() => onNavigate(edge.target)}><span>{edge.label}</span><code>{edge.target}</code></button>) : <p className="empty-state">없음</p>}</section>
        </>}
        {tab === "structured" && <JsonTree value={node.detail} />}
        {tab === "prompts" && (node.prompts?.length ? node.prompts.map((prompt) => <section key={prompt.sha256} className="prompt-block"><h3>{prompt.label}</h3><pre>{prompt.text}</pre><small>SHA-256 {prompt.sha256}</small></section>) : <p className="empty-state">이 노드에 직접 바인딩된 프롬프트가 없습니다.</p>)}
        {tab === "media" && (media.length ? <div className="media-grid">{media.map((file) => <div className="media-tile" key={file.path}><MediaPreview file={file} /><p>{file.path}</p></div>)}</div> : <p className="empty-state">이 노드에 직접 바인딩된 미디어가 없습니다.</p>)}
        {tab === "attempts" && <AttemptHistory attempts={node.attempts || []} />}
        {tab === "files" && (node.files?.length ? <div className="file-list">{node.files.map((file) => <a key={`${file.path}:${file.binding}`} href={mediaUrl(file.path)} target="_blank" rel="noreferrer"><span>{file.path}<small>{file.binding}</small></span><em>{file.kind} · {prettyBytes(file.bytes)}</em></a>)}</div> : <p className="empty-state">직접 바인딩된 파일이 없습니다.</p>)}
      </div>
    </aside>
  );
}

function PipelineDashboard() {
  const [snapshot, setSnapshot] = useState(null);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");
  const [lod, setLod] = useState("detail");
  const etagRef = useRef(null);
  const hasFittedRef = useRef(false);
  const { fitView, setCenter } = useReactFlow();

  const load = useCallback(async () => {
    const headers = etagRef.current ? { "If-None-Match": `"${etagRef.current}"` } : {};
    const response = await fetch("/api/snapshot", { headers, cache: "no-store" });
    if (response.status === 304) return;
    if (!response.ok) throw new Error((await response.json()).error || `HTTP ${response.status}`);
    const next = await response.json();
    etagRef.current = next.etag;
    setSnapshot(next);
    setError(null);
  }, []);

  useEffect(() => {
    load().catch((reason) => setError(String(reason)));
    const timer = window.setInterval(() => load().catch((reason) => setError(String(reason))), 2000);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!snapshot) return;
    let cancelled = false;
    layoutSnapshot(snapshot).then((next) => {
      if (cancelled) return;
      setGraph(next);
      if (!hasFittedRef.current) {
        hasFittedRef.current = true;
        window.setTimeout(() => fitView({ padding: 0.055, minZoom: 0.03, maxZoom: 0.9, duration: 350 }), 40);
      }
    }).catch((reason) => setError(String(reason)));
    return () => { cancelled = true; };
  }, [snapshot?.etag, fitView]);

  const entityById = useMemo(() => new Map((snapshot?.nodes || []).map((node) => [node.id, node])), [snapshot]);
  const selected = entityById.get(selectedId) || null;
  const lineage = useMemo(() => {
    if (!selectedId || !snapshot) return null;
    const connected = new Set([selectedId]);
    let changed = true;
    while (changed) {
      changed = false;
      snapshot.edges.forEach((edge) => {
        if (connected.has(edge.source) && !connected.has(edge.target)) { connected.add(edge.target); changed = true; }
        if (connected.has(edge.target) && !connected.has(edge.source)) { connected.add(edge.source); changed = true; }
      });
    }
    return connected;
  }, [selectedId, snapshot]);

  const visibleNodes = useMemo(() => graph.nodes.map((node) => {
    if (node.type !== "entity") return node;
    return { ...node, data: { ...node.data, dimmed: Boolean(lineage && !lineage.has(node.id)), lod } };
  }), [graph.nodes, lineage, lod]);
  const visibleEdges = useMemo(() => graph.edges.map((edge) => ({
    ...edge,
    label: lod === "detail" && (!lineage || (lineage.has(edge.source) && lineage.has(edge.target))) ? edge.data.label : undefined,
    style: { ...edge.style, opacity: lineage && !(lineage.has(edge.source) && lineage.has(edge.target)) ? 0.12 : 0.78 },
  })), [graph.edges, lineage, lod]);

  const focusNode = useCallback((id) => {
    setSelectedId(id);
    const flowNode = graph.nodes.find((node) => node.id === id);
    const parent = flowNode?.parentId ? graph.nodes.find((node) => node.id === flowNode.parentId) : null;
    if (flowNode) {
      setCenter((parent?.position.x || 0) + flowNode.position.x + ENTITY_WIDTH / 2, flowNode.position.y + ENTITY_HEIGHT / 2, { zoom: 1.05, duration: 350 });
    }
  }, [graph.nodes, setCenter]);

  const submitSearch = (event) => {
    event.preventDefault();
    const needle = query.trim().toLowerCase();
    if (!needle) return;
    const match = snapshot?.nodes.find((node) => `${node.id} ${node.title} ${node.subtitle}`.toLowerCase().includes(needle));
    if (match) focusNode(match.id);
  };

  if (error && !snapshot) return <div className="fatal"><h1>대시보드를 읽을 수 없습니다</h1><pre>{error}</pre></div>;
  if (!snapshot) return <div className="loading"><span></span><p>v3 산출물 계보를 읽는 중…</p></div>;

  return (
    <div className={`observer-app lod-${lod}`}>
      <header className="observer-toolbar">
        <div className="brand"><strong>Pipeline Observer</strong><span>READ ONLY</span></div>
        <div className="attempt-title"><b>{snapshot.attempt.id}</b><span>{snapshot.attempt.mode} · {snapshot.attempt.status} · {snapshot.attempt.current_stage || "complete"}</span></div>
        <form onSubmit={submitSearch}><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="노드, 신, 샷, 보드 검색" aria-label="그래프 검색" /><button>찾기</button></form>
        <div className="toolbar-stats"><span>{snapshot.stats.nodes} nodes</span><span>{snapshot.stats.media} media</span><span>{snapshot.stats.prompts} prompts</span>{snapshot.stats.unreferenced_files > 0 && <span className="warning">미연결 {snapshot.stats.unreferenced_files}</span>}</div>
      </header>
      <nav className="stage-strip" aria-label="파이프라인 단계">
        {snapshot.stages.map((stage) => <button key={stage.id} className={`tone-${statusTone(stage.status)}`} onClick={() => {
          const group = graph.nodes.find((node) => node.id === `stage-group:${stage.id}`);
          if (group) fitView({ nodes: graph.nodes.filter((node) => node.id === group.id || node.parentId === group.id), padding: 0.12, maxZoom: 1.05, duration: 350 });
        }}><small>{stage.id}</small><strong>{stage.title}</strong><span>{stage.status} · {stage.node_count}</span></button>)}
      </nav>
      <main className="graph-area">
        <ReactFlow
          nodes={visibleNodes}
          edges={visibleEdges}
          nodeTypes={nodeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          minZoom={0.03}
          maxZoom={2.5}
          fitView
          fitViewOptions={{ padding: 0.055 }}
          panOnScroll
          selectionOnDrag={false}
          onNodeClick={(_, node) => node.type === "entity" && focusNode(node.id)}
          onPaneClick={() => setSelectedId(null)}
          onMove={(_, viewport) => {
            const next = viewport.zoom < 0.34 ? "overview" : viewport.zoom < 0.72 ? "compact" : "detail";
            setLod((current) => current === next ? current : next);
          }}
          proOptions={{ hideAttribution: false }}
        >
          <Background gap={26} size={1} color="var(--observer-grid)" />
          <MiniMap pannable zoomable nodeStrokeWidth={2} maskColor="var(--observer-minimap-mask)" nodeColor={(node) => node.type === "stageGroup" ? "var(--observer-stage-mini)" : "var(--observer-node-mini)"} />
          <Controls showInteractive={false} />
        </ReactFlow>
        <div className="graph-legend"><span><i></i>직접 인풋·아웃풋</span><span><i className="receipt"></i>receipt</span><span><i className="warning"></i>미연결 파일</span><em>확대하면 노드 정보가 단계적으로 표시됩니다.</em></div>
        {error && <div className="refresh-error">갱신 실패 · {error}</div>}
        <Inspector node={selected} edges={snapshot.edges} onClose={() => setSelectedId(null)} onNavigate={focusNode} />
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode><ReactFlowProvider><PipelineDashboard /></ReactFlowProvider></React.StrictMode>,
);

import { useMemo } from "react";

const RELATION_COLORS = {
  alliance: "#10b981",
  ally: "#10b981",
  allied: "#10b981",
  rivalry: "#ef4444",
  rival: "#ef4444",
  hostile: "#ef4444",
  war: "#ef4444",
  trade: "#3b82f6",
  commerce: "#3b82f6",
  neutral: "#6b7280",
  vassal: "#f59e0b",
  federation: "#8b5cf6",
};

function getRelationColor(type) {
  if (!type) return "#6b7280";
  const lower = type.toLowerCase();
  for (const [key, color] of Object.entries(RELATION_COLORS)) {
    if (lower.includes(key)) return color;
  }
  return "#6b7280";
}

export default function WorldGraph({ config }) {
  const { nodes, edges, width, height } = useMemo(() => {
    const factions = config?.factions || [];
    const relations = config?.relations || config?.faction_relations || [];
    const w = 500;
    const h = 400;
    const cx = w / 2;
    const cy = h / 2;
    const radius = Math.min(cx, cy) - 60;

    const nodeList = factions.map((f, i) => {
      const angle = (2 * Math.PI * i) / factions.length - Math.PI / 2;
      const name = typeof f === "string" ? f : f.name || f.id || `F${i + 1}`;
      const id = typeof f === "string" ? f : f.id || f.name || `F${i + 1}`;
      return {
        id,
        name,
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      };
    });

    const nodeMap = {};
    nodeList.forEach((n) => {
      nodeMap[n.id] = n;
      nodeMap[n.name] = n;
    });

    const edgeList = relations
      .map((rel) => {
        const from =
          nodeMap[rel.from] ||
          nodeMap[rel.faction_a] ||
          nodeMap[rel.source];
        const to =
          nodeMap[rel.to] ||
          nodeMap[rel.faction_b] ||
          nodeMap[rel.target];
        if (!from || !to) return null;
        return {
          from,
          to,
          type: rel.type || rel.relation || "neutral",
          color: getRelationColor(rel.type || rel.relation),
        };
      })
      .filter(Boolean);

    return { nodes: nodeList, edges: edgeList, width: w, height: h };
  }, [config]);

  if (nodes.length === 0) {
    return (
      <div style={{ color: "var(--text-muted)", textAlign: "center", padding: 24 }}>
        Aucune faction a afficher.
      </div>
    );
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{
        background: "var(--bg-input)",
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--border)",
        display: "block",
        margin: "0 auto",
        maxWidth: "100%",
      }}
    >
      {/* Edges */}
      {edges.map((edge, i) => (
        <g key={`edge-${i}`}>
          <line
            x1={edge.from.x}
            y1={edge.from.y}
            x2={edge.to.x}
            y2={edge.to.y}
            stroke={edge.color}
            strokeWidth={2}
            strokeOpacity={0.6}
          />
          {/* Label on edge */}
          <text
            x={(edge.from.x + edge.to.x) / 2}
            y={(edge.from.y + edge.to.y) / 2 - 6}
            fill={edge.color}
            fontSize="9"
            textAnchor="middle"
            opacity={0.8}
          >
            {edge.type}
          </text>
        </g>
      ))}

      {/* Nodes */}
      {nodes.map((node, i) => (
        <g key={`node-${i}`}>
          <circle
            cx={node.x}
            cy={node.y}
            r={20}
            fill="var(--bg-card)"
            stroke="var(--accent)"
            strokeWidth={2}
          />
          <text
            x={node.x}
            y={node.y + 32}
            fill="var(--text-primary)"
            fontSize="11"
            textAnchor="middle"
            fontWeight="600"
          >
            {node.name.length > 14
              ? node.name.slice(0, 12) + "..."
              : node.name}
          </text>
          {/* Initial letter in circle */}
          <text
            x={node.x}
            y={node.y + 4}
            fill="var(--accent)"
            fontSize="13"
            textAnchor="middle"
            fontWeight="700"
          >
            {node.name.charAt(0).toUpperCase()}
          </text>
        </g>
      ))}

      {/* Legend */}
      {edges.length > 0 && (
        <g transform={`translate(10, ${height - 60})`}>
          {[...new Set(edges.map((e) => e.type))].slice(0, 4).map((type, i) => (
            <g key={type} transform={`translate(${i * 100}, 0)`}>
              <rect
                x={0}
                y={0}
                width={10}
                height={10}
                fill={getRelationColor(type)}
                rx={2}
              />
              <text x={14} y={9} fill="var(--text-secondary)" fontSize="9">
                {type}
              </text>
            </g>
          ))}
        </g>
      )}
    </svg>
  );
}

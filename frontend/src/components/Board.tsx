import { Fragment, useRef, useState, type CSSProperties, type DragEvent, type MouseEvent, type ReactNode } from "react";
import type { Stage } from "../types";

/** Private drag payload, so dropping stray text on a column does nothing. */
export const DRAG_TYPE = "application/x-coach-id";

export type DragProps = {
  dragging: boolean;
  disabled?: boolean; // view-only users cannot move cards
  onDragStart: (id: number) => void;
  onDragEnd: () => void;
};

type Item = { id: number; status: string; not_interested_at?: string | null };

type Props<T extends Item> = {
  stages: Stage[];
  items: T[];
  sort: (a: T, b: T) => number;
  onMove: (id: number, status: string) => void;
  renderCard: (item: T, stageLabel: string, drag: DragProps) => ReactNode;
  readOnly?: boolean;
};

/** Kanban board shared by both tabs: one column per status, all visible at once. */
export default function Board<T extends Item>({ stages, items, sort, onMove, renderCard, readOnly = false }: Props<T>) {
  const [dragId, setDragId] = useState<number | null>(null);
  const [overStage, setOverStage] = useState<string | null>(null);
  const [unfolded, setUnfolded] = useState<Set<string>>(new Set()); // columns showing their set-aside cards
  const toggleFold = (key: string) =>
    setUnfolded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const endDrag = () => {
    setDragId(null);
    setOverStage(null);
  };

  return (
    <div className="board" style={{ "--cols": stages.length } as CSSProperties}>
      {stages.map((stage) => {
        const all = items.filter((a) => a.status === stage.key).sort(sort);
        const cards = all.filter((a) => !a.not_interested_at);
        const parked = all.filter((a) => a.not_interested_at);
        const open = unfolded.has(stage.key);
        return (
          <section
            key={stage.key}
            className={`column stage-${stage.key}${overStage === stage.key ? " is-over" : ""}`}
            onDragOver={(e) => {
              if (readOnly || !e.dataTransfer.types.includes(DRAG_TYPE)) return;
              e.preventDefault();
              if (overStage !== stage.key) setOverStage(stage.key);
            }}
            onDragLeave={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node)) setOverStage(null);
            }}
            onDrop={(e) => {
              const id = Number(e.dataTransfer.getData(DRAG_TYPE));
              if (readOnly || !id) return;
              e.preventDefault();
              endDrag();
              onMove(id, stage.key);
            }}
          >
            <header className="column-head">
              <span className="dot" />
              <h2>{stage.label}</h2>
              <span className="count">{cards.length}</span>
            </header>
            <div className="column-body">
              {cards.map((item) => (
                <Fragment key={item.id}>
                  {renderCard(item, stage.label, { dragging: dragId === item.id, disabled: readOnly, onDragStart: setDragId, onDragEnd: endDrag })}
                </Fragment>
              ))}
              {cards.length === 0 && <div className="empty">{readOnly ? "Nothing here" : "Drop a card here"}</div>}
              {parked.length > 0 && (
                <button className="parked-toggle" onClick={() => toggleFold(stage.key)} aria-expanded={open}>
                  {open ? "Hide" : "Show"} {parked.length} not interested
                </button>
              )}
              {open && parked.map((item) => (
                <div key={item.id} className="parked">
                  {renderCard(item, stage.label, { dragging: dragId === item.id, disabled: readOnly, onDragStart: setDragId, onDragEnd: endDrag })}
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

/** Card clicks: one click opens the card small (or closes it again), a double click opens the full sheet.
 * The single click waits a moment so the first click of a double click does not also toggle the card. */
export function useCardClicks(onFull: () => void) {
  const [open, setOpen] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const onClick = (e: MouseEvent) => {
    window.clearTimeout(timer.current);
    if (e.detail >= 2) onFull();
    else timer.current = window.setTimeout(() => setOpen((o) => !o), 200);
  };
  return { open, setOpen, onClick };
}

/** Attributes that make a card draggable onto the board's columns. */
export function dragHandlers(id: number, drag: DragProps) {
  if (drag.disabled) return {};
  return {
    draggable: true,
    onDragStart: (e: DragEvent) => {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData(DRAG_TYPE, String(id));
      drag.onDragStart(id);
    },
    onDragEnd: drag.onDragEnd,
  };
}

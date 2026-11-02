import { Button, cn } from "../ui";

/** The bottom bar of a form page: what state it is in, 되돌리기 and 저장. */
export function SaveBar({ dirty, busy, invalid, error, note, onReset }: {
  dirty: boolean; busy: boolean; invalid: boolean; error: string; note?: string; onReset: () => void;
}) {
  return (
    <div className={cn("sticky bottom-0 mt-6 flex items-center gap-3 rounded-b-2xl border-t border-line bg-surface/95 px-6 py-3 backdrop-blur", !dirty && "opacity-90")}>
      <span className="flex-1 text-[13px]" role="status">
        {error ? <span className="font-medium text-err-fg">{error}</span>
          : dirty ? <span className="text-warn-fg">저장하지 않은 변경이 있어요{note ? `. ${note}` : ""}</span>
          : <span className="text-muted">모든 변경을 저장했어요</span>}
      </span>
      <Button type="button" disabled={!dirty || busy} onClick={onReset}>되돌리기</Button>
      <Button type="submit" variant="primary" loading={busy} disabled={!dirty || invalid}>저장</Button>
    </div>
  );
}

"use client";

import { ReactNode } from "react";
import { Loader2 } from "lucide-react";

export type Column<T> = {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  width?: string;
  align?: "left" | "right" | "center";
};

export type DataTablePagination = {
  page: number;
  pageSize: number;
  total?: number;
  onPageChange: (page: number) => void;
};

type DataTableProps<T> = {
  columns: Column<T>[];
  data: T[];
  loading?: boolean;
  emptyState?: { title: string; hint?: string };
  onRowClick?: (row: T) => void;
  rowActions?: (row: T) => ReactNode;
  toolbar?: ReactNode;
  pagination?: DataTablePagination;
  getRowKey?: (row: T, index: number) => string;
};

export function DataTable<T>(props: DataTableProps<T>) {
  const {
    columns,
    data,
    loading,
    emptyState,
    onRowClick,
    rowActions,
    toolbar,
    pagination,
    getRowKey,
  } = props;

  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden">
      {toolbar && (
        <div className="px-4 py-3 border-b border-slate-100 bg-slate-50/50">
          {toolbar}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-48 gap-2 text-slate-400 text-sm">
          <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
          Carregando…
        </div>
      ) : data.length === 0 && emptyState ? (
        <div className="text-center py-16 px-4">
          <p className="text-slate-500 font-medium">{emptyState.title}</p>
          {emptyState.hint && (
            <p className="text-slate-400 text-sm mt-1">{emptyState.hint}</p>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                {columns.map((c) => (
                  <th
                    key={c.key}
                    className="px-5 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide"
                    style={{
                      width: c.width,
                      textAlign: c.align ?? "left",
                    }}
                  >
                    {c.header}
                  </th>
                ))}
                {rowActions && (
                  <th className="px-5 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">
                    Ações
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {data.map((row, i) => {
                const key = getRowKey ? getRowKey(row, i) : String(i);
                const clickable = !!onRowClick;
                return (
                  <tr
                    key={key}
                    onClick={() => onRowClick?.(row)}
                    className={`transition-colors ${
                      clickable
                        ? "hover:bg-slate-50/50 cursor-pointer"
                        : "hover:bg-slate-50/30"
                    }`}
                  >
                    {columns.map((c) => (
                      <td
                        key={c.key}
                        className="px-5 py-3 text-slate-600"
                        style={{ textAlign: c.align ?? "left" }}
                      >
                        {c.render
                          ? c.render(row)
                          : String((row as Record<string, unknown>)[c.key] ?? "—")}
                      </td>
                    ))}
                    {rowActions && (
                      <td
                        className="px-5 py-3"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="flex items-center gap-1">
                          {rowActions(row)}
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {pagination && (
        <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 bg-slate-50/50">
          <span className="text-xs text-slate-500">
            {pagination.total !== undefined ? (
              <>
                Página {pagination.page} · {pagination.total}{" "}
                {pagination.total === 1 ? "item" : "itens"}
              </>
            ) : (
              <>
                Exibindo {data.length} — página {pagination.page}
              </>
            )}
          </span>
          <div className="flex gap-2">
            <button
              disabled={pagination.page <= 1}
              onClick={() => pagination.onPageChange(pagination.page - 1)}
              className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-white text-slate-600 disabled:opacity-40 hover:bg-slate-50"
            >
              Anterior
            </button>
            <button
              disabled={
                data.length < pagination.pageSize ||
                (pagination.total !== undefined &&
                  pagination.page * pagination.pageSize >= pagination.total)
              }
              onClick={() => pagination.onPageChange(pagination.page + 1)}
              className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-white text-slate-600 disabled:opacity-40 hover:bg-slate-50"
            >
              Próxima
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

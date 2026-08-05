/** Hoofdscherm: overzicht van verzamelorders met de mogelijkheid er één opnieuw
 * te genereren. */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { haalOverzichtOp } from "./api.js";
import type { Verzamelorder } from "../shared/types.js";
import { RegenereerModal } from "./components/RegenereerModal.js";
import { VerzamelorderLijst } from "./components/VerzamelorderLijst.js";

export function App() {
  const queryClient = useQueryClient();
  const [gekozen, setGekozen] = useState<Verzamelorder | null>(null);

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["verzamelorders"],
    queryFn: haalOverzichtOp,
  });

  const ververs = () => {
    void queryClient.invalidateQueries({ queryKey: ["verzamelorders"] });
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-4 px-6 py-5">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">
              Weekrapportage De Lokalist
            </h1>
            <p className="text-sm text-slate-500">
              Verzamelorders in MendriX — klik er één aan om het rapport opnieuw
              te genereren.
            </p>
          </div>
          <button
            type="button"
            onClick={ververs}
            disabled={isFetching}
            className="ml-auto rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {isFetching ? "Bezig…" : "Vernieuwen"}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-6">
        {isPending && (
          <p className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-500">
            Verzamelorders ophalen uit MendriX…
          </p>
        )}

        {isError && (
          <div className="rounded-xl border border-red-300 bg-red-50 p-6">
            <p className="font-semibold text-red-900">Ophalen mislukt</p>
            <p className="mt-1 text-sm text-red-800">
              {error instanceof Error ? error.message : "Onbekende fout."}
            </p>
            <button
              type="button"
              onClick={() => void refetch()}
              className="mt-3 rounded-lg bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-700"
            >
              Opnieuw proberen
            </button>
          </div>
        )}

        {data && (
          <VerzamelorderLijst
            orders={data.verzamelorders}
            onKies={setGekozen}
          />
        )}
      </main>

      {gekozen && data && (
        <RegenereerModal
          order={gekozen}
          emailInstellingen={data.email}
          onSluit={() => setGekozen(null)}
          onGeslaagd={ververs}
        />
      )}
    </div>
  );
}

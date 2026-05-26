import "./index.css"

export function App() {
  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center">
      <div className="text-center">
        <h1 className="text-5xl font-bold text-white mb-4" style={{ fontFamily: "Heebo" }}>
          PandaPower
        </h1>
        <p className="text-xl text-slate-300 mb-8">מערכת גיוס AI</p>
        <div className="inline-block px-4 py-2 bg-slate-800 rounded-lg border border-slate-700">
          <p className="text-sm text-slate-400">Phase 1 — Foundation</p>
        </div>
      </div>
    </div>
  )
}

export default App

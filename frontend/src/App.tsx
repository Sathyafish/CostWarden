import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { Header, type Tab } from './components/Header'
import { Ask } from './pages/Ask'
import { Overview } from './pages/Overview'
import { Runs } from './pages/Runs'
import type { Info } from './types'

export default function App() {
  const [tab, setTab] = useState<Tab>('overview')
  const [info, setInfo] = useState<Info | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const loadInfo = useCallback(() => {
    api.info().then(setInfo).catch(() => setInfo(null))
  }, [])

  useEffect(loadInfo, [loadInfo])

  const bump = () => setReloadKey((k) => k + 1)

  return (
    <div className="app">
      <Header
        tab={tab}
        onTab={setTab}
        info={info}
        onConfigChanged={() => {
          loadInfo()
          bump()
        }}
      />
      <main className="main">
        {tab === 'overview' && <Overview info={info} reloadKey={reloadKey} />}
        {tab === 'ask' && <Ask />}
        {tab === 'runs' && <Runs onChanged={bump} />}
      </main>
      <footer className="footer">CostWarden · Guard the cloud. Keep the savings.</footer>
    </div>
  )
}

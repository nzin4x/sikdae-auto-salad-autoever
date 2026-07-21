import { useEffect, useState } from 'react'
import { api } from './api'
import Register from './Register'
import Dashboard from './Dashboard'
import Stats from './Stats'
import './App.css'

function getDeviceFingerprint() {
  let fp = localStorage.getItem('deviceFingerprint')
  if (!fp) {
    fp = crypto.randomUUID()
    localStorage.setItem('deviceFingerprint', fp)
  }
  return fp
}

export default function App() {
  const [stage, setStage] = useState('loading') // loading | email | code | register | dashboard
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showStats, setShowStats] = useState(false)
  const fingerprint = getDeviceFingerprint()

  useEffect(() => {
    api
      .checkDevice(fingerprint)
      .then((res) => {
        if (res.authenticated) {
          setEmail(res.email)
          setStage('dashboard')
        } else {
          setStage('email')
        }
      })
      .catch(() => setStage('email'))
  }, [])

  async function handleSendCode(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await api.sendCode(email)
      setStage('code')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleVerifyCode(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const res = await api.verifyCode(email, code, fingerprint)
      setStage(res.hasAccount ? 'dashboard' : 'register')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleLogout() {
    try {
      await api.logout(email, fingerprint)
    } catch {
      // 로컬 로그아웃은 서버 호출 실패와 무관하게 진행
    }
    setEmail('')
    setCode('')
    setStage('email')
  }

  if (stage === 'loading') {
    return (
      <div className="container center">
        <div className="app-title">🍱</div>
        <p className="muted">불러오는 중...</p>
      </div>
    )
  }

  return (
    <div className="container">
      <div className="app-title">🍱 식대오토샐러드</div>
      <div className="app-subtitle">식권대장 자동예약 도우미</div>
      {error && <p className="error">⚠️ {error}</p>}

      {stage === 'email' && (
        <form onSubmit={handleSendCode}>
          <p>📧 이메일로 로그인합니다.</p>
          <input type="email" placeholder="이메일" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <button type="submit" className="primary" disabled={busy}>
            {busy ? '보내는 중...' : '✉️ 인증코드 받기'}
          </button>
        </form>
      )}

      {stage === 'code' && (
        <form onSubmit={handleVerifyCode}>
          <p>🔐 {email}로 전송된 인증코드를 입력하세요.</p>
          <input type="text" placeholder="인증코드 6자리" value={code} onChange={(e) => setCode(e.target.value)} required />
          <button type="submit" className="primary" disabled={busy}>{busy ? '확인 중...' : '✅ 확인'}</button>
        </form>
      )}

      {stage === 'register' && (
        <Register email={email} fingerprint={fingerprint} onDone={() => setStage('dashboard')} />
      )}

      {stage === 'dashboard' && <Dashboard email={email} fingerprint={fingerprint} onLogout={handleLogout} />}

      <footer className="app-footer">
        <a href="https://github.com/nzin4x/sikdae-auto-salad-autoever" target="_blank" rel="noopener noreferrer">
          🐙 GitHub
        </a>
        <span className="footer-divider">·</span>
        <a href="#" onClick={(e) => { e.preventDefault(); setShowStats(true) }}>📊 Stat</a>
      </footer>

      {showStats && <Stats onClose={() => setShowStats(false)} />}
    </div>
  )
}

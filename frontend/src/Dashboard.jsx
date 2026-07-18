import { useEffect, useState } from 'react'
import { api } from './api'
import Settings from './Settings'

function isPast1PmKst() {
  const now = new Date()
  const utc = now.getTime() + now.getTimezoneOffset() * 60000
  const kst = new Date(utc + 9 * 60 * 60 * 1000)
  return kst.getHours() >= 13
}

export default function Dashboard({ email, onLogout }) {
  const [settings, setSettings] = useState(null)
  const [reservationInfo, setReservationInfo] = useState(null)
  const [reservationLoading, setReservationLoading] = useState(true)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const [showSettings, setShowSettings] = useState(false)

  function refresh() {
    api.getSettings(email).then(setSettings).catch((err) => setMessage({ type: 'error', text: err.message }))
    setReservationLoading(true)
    api
      .checkReservation(email)
      .then(setReservationInfo)
      .catch((err) => setMessage({ type: 'error', text: err.message }))
      .finally(() => setReservationLoading(false))
  }

  useEffect(refresh, [email])

  async function handleToggle() {
    if (!settings) return
    setBusy(true)
    try {
      const nextEnabled = !settings.isActive
      await api.toggleAutoReservation(email, nextEnabled)
      setSettings((prev) => ({ ...prev, isActive: nextEnabled }))
      setMessage({ type: 'success', text: nextEnabled ? '자동 예약이 활성화되었습니다' : '자동 예약이 비활성화되었습니다' })
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  async function handleImmediateReservation() {
    if (!confirm('지금 바로 예약을 진행하시겠습니까? (다음 근무일 예약이 시도됩니다)')) return
    setBusy(true)
    setMessage(null)
    try {
      const result = await api.makeImmediateReservation(email)
      setMessage({ type: result.success ? 'success' : 'error', text: result.message })
      refresh()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  async function handleCancel() {
    if (!confirm('❌ 가장 가까운 예약을 취소할까요?')) return
    setBusy(true)
    setMessage(null)
    try {
      const result = await api.cancelReservation(email)
      setMessage({ type: 'success', text: `✅ ${result.canceledMenu || ''} ${result.message}`.trim() })
      refresh()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  async function handleDeleteAccount() {
    if (!confirm('진짜 탈퇴하시겠습니까? 모든 정보가 삭제되며 복구할 수 없습니다.')) return
    try {
      await api.deleteAccount(email)
      alert('계정이 삭제되었습니다.')
      onLogout()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
  }

  const reservations = reservationInfo?.reservations || []
  const hasNextWorkdayReservation = reservationInfo?.hasNextWorkdayReservation || false

  return (
    <div>
      <p>👋 <strong>{email}</strong>님, 안녕하세요!</p>
      {message && <p className={message.type === 'error' ? 'error' : 'success'}>{message.text}</p>}

      {settings && (
        <div className="card toggle-card" data-active={settings.isActive}>
          <div>
            <div className="card-title">{settings.isActive ? '🟢' : '🟠'} 자동 예약 {settings.isActive ? '활성화' : '비활성화'}</div>
            <div className="muted">{settings.isActive ? '평일 13:00에 자동으로 예약됩니다' : '자동 예약이 일시 중지되었습니다'}</div>
          </div>
          <label className="switch">
            <input type="checkbox" checked={settings.isActive} onChange={handleToggle} disabled={busy} />
            <span />
          </label>
        </div>
      )}

      <div className="section-title">🍽️ 예약 현황</div>
      {reservationLoading ? (
        <div className="card muted center">⏳ 불러오는 중...</div>
      ) : reservations.length > 0 ? (
        <div className="reservation-grid">
          {reservations.map((r) => (
            <div className="card reservation-card" key={r.date}>
              <span className={`badge ${r.label === '오늘' ? 'badge-today' : 'badge-upcoming'}`}>
                {r.label === '오늘' ? '📌' : '🗓️'} {r.label} ({r.date})
              </span>
              <div className="card-title">{r.menus.join(', ')}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card muted center">🈳 예약 내역이 없습니다</div>
      )}

      {reservations.length > 0 && (
        <button className="danger" onClick={handleCancel} disabled={busy}>❌ 가장 가까운 예약 취소</button>
      )}

      {!reservationLoading && isPast1PmKst() && !hasNextWorkdayReservation && (
        <button className="primary" onClick={handleImmediateReservation} disabled={busy}>
          {busy ? '⏳ 처리 중...' : '⚡ 즉시 예약 (다음 근무일)'}
        </button>
      )}

      <button onClick={() => setShowSettings(true)}>⚙️ 설정</button>
      <button onClick={onLogout}>🚪 로그아웃</button>

      <div className="center" style={{ marginTop: 14 }}>
        <a href="#" className="muted-link" onClick={(e) => { e.preventDefault(); handleDeleteAccount() }}>
          🗑️ 개인정보 삭제 (탈퇴)
        </a>
      </div>

      {showSettings && (
        <Settings
          email={email}
          onClose={() => setShowSettings(false)}
          onSaved={() => {
            setShowSettings(false)
            setMessage({ type: 'success', text: '설정이 저장되었습니다' })
            refresh()
          }}
        />
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { api } from './api'
import Calendar from './Calendar'

export default function Settings({ email, onClose, onSaved }) {
  const [menuPreference, setMenuPreference] = useState([])
  const [deliverySpotKeyword, setDeliverySpotKeyword] = useState('')
  const [mealcUserId, setMealcUserId] = useState('')
  const [mealcPassword, setMealcPassword] = useState('')
  const [exclusionDates, setExclusionDates] = useState([])
  const [masterPassword, setMasterPassword] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .getSettings(email)
      .then((s) => {
        setMenuPreference(s.menuPreference || [])
        setDeliverySpotKeyword(s.deliverySpotKeyword || '')
        setExclusionDates(s.exclusionDates || [])
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [email])

  function moveMenu(index, direction) {
    setMenuPreference((prev) => {
      const next = [...prev]
      const target = index + direction
      if (target < 0 || target >= next.length) return prev
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  function removeMenu(index) {
    setMenuPreference((prev) => prev.filter((_, i) => i !== index))
  }

  function addMenu(value) {
    if (!value.trim()) return
    setMenuPreference((prev) => [...prev, value.trim()])
  }

  function toggleExclusionDate(dateStr) {
    setExclusionDates((prev) =>
      prev.includes(dateStr) ? prev.filter((d) => d !== dateStr) : [...prev, dateStr].sort()
    )
  }

  async function handleSave() {
    setError('')
    if (!masterPassword) {
      setError('🔒 마스터 패스워드를 입력해야 저장할 수 있습니다.')
      return
    }
    setSaving(true)
    try {
      await api.updateSettings({
        email,
        masterPassword,
        menuPreference,
        deliverySpotKeyword,
        mealcUserId: mealcUserId || undefined,
        mealcPassword: mealcPassword || undefined,
      })
      await api.updateExclusionDates(email, exclusionDates)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>⚙️ 설정</h2>
        {error && <p className="error">{error}</p>}
        {loading ? (
          <p className="center muted">불러오는 중...</p>
        ) : (
          <>
            <label>🍽️ 선호 메뉴 순서</label>
            <ul className="menu-list">
              {menuPreference.map((menu, i) => (
                <li key={`${menu}-${i}`}>
                  <span>{menu}</span>
                  <span>
                    <button type="button" onClick={() => moveMenu(i, -1)} disabled={i === 0}>⬆️</button>
                    <button type="button" onClick={() => moveMenu(i, 1)} disabled={i === menuPreference.length - 1}>⬇️</button>
                    <button type="button" onClick={() => removeMenu(i)}>🗑️</button>
                  </span>
                </li>
              ))}
              {menuPreference.length === 0 && <li className="muted">등록된 선호 메뉴 없음</li>}
            </ul>
            <AddMenuInput onAdd={addMenu} />

            <label>📍 배송지 키워드</label>
            <input value={deliverySpotKeyword} onChange={(e) => setDeliverySpotKeyword(e.target.value)} placeholder="예: 4층" />

            <label>🆔 식권대장 아이디 변경 (선택)</label>
            <input value={mealcUserId} onChange={(e) => setMealcUserId(e.target.value)} placeholder="변경할 경우에만 입력" />

            <label>🔑 식권대장 비밀번호 변경 (선택)</label>
            <input type="password" value={mealcPassword} onChange={(e) => setMealcPassword(e.target.value)} placeholder="변경할 경우에만 입력" />

            <label>📅 제외일 (휴가 등 예약 안 할 날 — 달력에서 날짜를 눌러 선택/해제)</label>
            <Calendar selectedDates={exclusionDates} onToggleDate={toggleExclusionDate} />
            <div className="chip-list">
              {exclusionDates.length > 0 ? (
                exclusionDates.map((date) => (
                  <span key={date} className="chip">
                    {date}
                    <button type="button" onClick={() => toggleExclusionDate(date)}>✕</button>
                  </span>
                ))
              ) : (
                <span className="muted">선택된 제외일 없음</span>
              )}
            </div>

            <label>🔒 마스터 패스워드 (저장하려면 필수)</label>
            <input type="password" value={masterPassword} onChange={(e) => setMasterPassword(e.target.value)} required />

            <div className="row" style={{ marginTop: 16 }}>
              <button type="button" onClick={onClose} disabled={saving}>닫기</button>
              <button type="button" className="primary" onClick={handleSave} disabled={saving}>
                {saving ? '저장 중...' : '💾 저장'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function AddMenuInput({ onAdd }) {
  const [value, setValue] = useState('')
  return (
    <div className="row">
      <input placeholder="메뉴 키워드 추가 (예: 헬시)" value={value} onChange={(e) => setValue(e.target.value)} />
      <button
        type="button"
        onClick={() => {
          onAdd(value)
          setValue('')
        }}
      >
        ➕ 추가
      </button>
    </div>
  )
}

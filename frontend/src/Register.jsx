import { useState } from 'react'
import { api } from './api'

export default function Register({ email, fingerprint, onDone }) {
  const [mealcUserId, setMealcUserId] = useState('')
  const [mealcPassword, setMealcPassword] = useState('')
  const [menuPreference, setMenuPreference] = useState('샌드위치,샐러드')
  const [deliverySpotKeyword, setDeliverySpotKeyword] = useState('4층')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    setBusy(true)
    try {
      await api.register({
        email,
        mealcUserId,
        mealcPassword,
        menuPreference: menuPreference.split(',').map((s) => s.trim()).filter(Boolean),
        deliverySpotKeyword,
        deviceFingerprint: fingerprint,
      })
      setDone(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <div className="center">
        <div style={{ fontSize: 48, margin: '20px 0' }}>🎉</div>
        <p>가입 완료! 이제 자동으로 점심을 챙겨드릴게요.</p>
        <button className="primary" onClick={onDone}>대시보드로 이동 →</button>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit}>
      <p>👋 처음 오셨네요. 식권대장 계정을 등록해주세요.</p>
      {error && <p className="error">⚠️ {error}</p>}
      <label>🆔 식권대장 아이디</label>
      <input placeholder="식권대장 아이디" value={mealcUserId} onChange={(e) => setMealcUserId(e.target.value)} required />
      <label>🔑 식권대장 비밀번호</label>
      <input type="password" placeholder="식권대장 비밀번호" value={mealcPassword} onChange={(e) => setMealcPassword(e.target.value)} required />
      <p className="hint">
        ⚠️ 비밀번호는 암호화되어 저장되지만, 서버 관리자는 암호화 키로 언제든 복호화할 수 있습니다.
        <strong> 노출되어도 크게 지장이 없는 비밀번호로 식권대장 앱에서 먼저 변경한 뒤</strong> 가입해주세요.
        못 미더우시면 GitHub 소스코드를 직접 확인해보세요.
        <br />⚠️ 자동 예약이 실행될 시, 기존 식권대장 앱의 로그인 세션은 비활성화됩니다.
      </p>
      <label>🍽️ 선호 메뉴</label>
      <input placeholder="쉼표로 구분, 예: 샌드위치,샐러드" value={menuPreference} onChange={(e) => setMenuPreference(e.target.value)} />
      <p className="hint">
        💡 선호 메뉴 순서대로 이름에 포함된 메뉴를 찾아 예약을 시도합니다. 케이크 등의 특식에는 적용되지 않습니다.
      </p>
      <label>📍 배송지 키워드</label>
      <input placeholder="예: 4층" value={deliverySpotKeyword} onChange={(e) => setDeliverySpotKeyword(e.target.value)} />
      <button type="submit" className="primary" disabled={busy}>{busy ? '가입 처리 중...' : '🚀 가입하기'}</button>
    </form>
  )
}

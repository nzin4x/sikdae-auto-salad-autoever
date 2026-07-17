import { useState } from 'react'
import { api } from './api'

export default function Register({ email, fingerprint, onDone }) {
  const [mealcUserId, setMealcUserId] = useState('')
  const [mealcPassword, setMealcPassword] = useState('')
  const [masterPassword, setMasterPassword] = useState('')
  const [menuPreference, setMenuPreference] = useState('샌드위치,샐러드')
  const [deliverySpotKeyword, setDeliverySpotKeyword] = useState('4층')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    if (masterPassword.length < 8) {
      setError('마스터 패스워드는 8자 이상이어야 합니다.')
      return
    }
    if (masterPassword === mealcPassword) {
      setError('마스터 패스워드는 식권대장 비밀번호와 달라야 합니다.')
      return
    }

    setBusy(true)
    try {
      await api.register({
        email,
        mealcUserId,
        mealcPassword,
        masterPassword,
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
      <label>🔒 마스터 패스워드</label>
      <input
        type="password"
        placeholder="8자 이상, 식권대장 비번과 다르게"
        value={masterPassword}
        onChange={(e) => setMasterPassword(e.target.value)}
        required
      />
      <p className="hint">
        🔐 마스터 패스워드는 설정 변경/탈퇴 시에만 사용되며 <strong>서버에는 해시로만 저장되어 평문은 어디에도 남지 않습니다</strong>.
        분실하면 복구할 수 없으니(재가입 필요) 꼭 기억해두세요. 못 미더우시면 GitHub 소스코드(core/crypto.py)를 직접 확인해보세요.
      </p>
      <label>🍽️ 선호 메뉴</label>
      <input placeholder="쉼표로 구분, 예: 샌드위치,샐러드" value={menuPreference} onChange={(e) => setMenuPreference(e.target.value)} />
      <label>📍 배송지 키워드</label>
      <input placeholder="예: 4층" value={deliverySpotKeyword} onChange={(e) => setDeliverySpotKeyword(e.target.value)} />
      <button type="submit" className="primary" disabled={busy}>{busy ? '가입 처리 중...' : '🚀 가입하기'}</button>
    </form>
  )
}

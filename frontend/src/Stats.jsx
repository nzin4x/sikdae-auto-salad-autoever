import { useEffect, useState } from 'react'
import { api } from './api'

export default function Stats({ onClose }) {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getStats().then(setStats).catch((err) => setError(err.message))
  }, [])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>📊 서비스 현황</h2>
        {error && <p className="error">{error}</p>}
        {!stats && !error && <p className="center muted">불러오는 중...</p>}

        {stats && (
          <>
            <div className="stat-grid">
              <div className="stat-tile">
                <div className="stat-value">{stats.totalUsers} / {stats.maxUsers}</div>
                <div className="stat-label">👥 가입자 수</div>
              </div>
              <div className="stat-tile">
                <div className="stat-value">{stats.activeUsers}</div>
                <div className="stat-label">🟢 예약 활성화 인원</div>
              </div>
              <div className="stat-tile">
                <div className="stat-value">{stats.usersWithReservationHistory}</div>
                <div className="stat-label">✅ 예약 성공 이력 보유</div>
              </div>
              <div className="stat-tile">
                <div className="stat-value">{stats.topMenuPreference || '-'}</div>
                <div className="stat-label">🍽️ 최애 메뉴 1순위</div>
              </div>
              <div className="stat-tile">
                <div className="stat-value">{stats.topDeliverySpot || '-'}</div>
                <div className="stat-label">📍 최다 배송지</div>
              </div>
            </div>

            <label>🗓️ 이번달 공휴일 (자동예약 건너뜀)</label>
            {stats.holidaysThisMonth?.length > 0 ? (
              <div className="chip-list">
                {stats.holidaysThisMonth.map((h) => (
                  <span key={h.date} className="chip chip-neutral">
                    {h.date} ({h.weekday})
                  </span>
                ))}
              </div>
            ) : (
              <p className="muted">이번달 등록된 공휴일 없음</p>
            )}

            <label>🙈 다른 회원들이 등록한 제외일 (참고용, 익명)</label>
            <p className="hint">
              누가 어떤 날을 제외했는지는 알 수 없고, 날짜별 인원수만 보여줍니다. 회사 워크샵/휴가철 등
              여러 명이 겹쳐서 제외해둔 날이 있다면 참고하세요.
            </p>
            {stats.commonExclusionDates?.length > 0 ? (
              <div className="chip-list">
                {stats.commonExclusionDates.map((d) => (
                  <span key={d.date} className="chip chip-neutral">
                    {d.date} · {d.count}명
                  </span>
                ))}
              </div>
            ) : (
              <p className="muted">앞으로 등록된 제외일 없음</p>
            )}
          </>
        )}

        <button type="button" onClick={onClose} style={{ marginTop: 16 }}>닫기</button>
      </div>
    </div>
  )
}

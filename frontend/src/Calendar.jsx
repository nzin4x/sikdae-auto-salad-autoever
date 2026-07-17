import { useState } from 'react'

function toDateStr(year, month, day) {
  const mm = String(month + 1).padStart(2, '0')
  const dd = String(day).padStart(2, '0')
  return `${year}-${mm}-${dd}`
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

export default function Calendar({ selectedDates, onToggleDate }) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const [cursor, setCursor] = useState(new Date(today.getFullYear(), today.getMonth(), 1))

  const year = cursor.getFullYear()
  const month = cursor.getMonth()
  const firstWeekday = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const cells = []
  for (let i = 0; i < firstWeekday; i++) cells.push(null)
  for (let day = 1; day <= daysInMonth; day++) cells.push(day)

  function changeMonth(delta) {
    setCursor(new Date(year, month + delta, 1))
  }

  return (
    <div className="calendar">
      <div className="calendar-header">
        <button type="button" onClick={() => changeMonth(-1)}>◀</button>
        <span>
          {year}년 {month + 1}월
        </span>
        <button type="button" onClick={() => changeMonth(1)}>▶</button>
      </div>
      <div className="calendar-grid">
        {WEEKDAYS.map((w) => (
          <div key={w} className="calendar-weekday">{w}</div>
        ))}
        {cells.map((day, i) => {
          if (day === null) return <div key={`blank-${i}`} />
          const dateStr = toDateStr(year, month, day)
          const cellDate = new Date(year, month, day)
          const isPast = cellDate < today
          const isSelected = selectedDates.includes(dateStr)
          return (
            <button
              type="button"
              key={dateStr}
              className={`calendar-day${isSelected ? ' selected' : ''}`}
              disabled={isPast}
              onClick={() => onToggleDate(dateStr)}
            >
              {day}
            </button>
          )
        })}
      </div>
    </div>
  )
}

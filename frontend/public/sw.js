self.addEventListener('push', (event) => {
  let payload = { title: '식대오토샐러드', body: '' }
  try {
    payload = event.data.json()
  } catch {
    // 데이터가 없거나 JSON이 아니면 기본값 사용
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/og-image.png',
      data: { url: payload.url || '/' },
    })
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/'
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((clientsList) => {
      const existing = clientsList.find((c) => c.url === url)
      if (existing) return existing.focus()
      return self.clients.openWindow(url)
    })
  )
})

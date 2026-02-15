import { useEffect, useState } from "react"
import { getHealth } from "@/lib/api"

export function useConnectionStatus() {
  const [connected, setConnected] = useState(true)

  useEffect(() => {
    let active = true

    const check = async () => {
      try {
        await getHealth()
        if (active) setConnected(true)
      } catch {
        if (active) setConnected(false)
      }
    }

    check()
    const id = setInterval(check, 30000)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [])

  return connected
}

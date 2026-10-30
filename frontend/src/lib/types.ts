export interface SensorData {
  voltage: number | null
  current: number | null
  temperature: number | null
  light_intensity: number | null
  humidity: number | null
  thermistor_temp: number | null
  efficiency?: number | null
  irradiance: number | null
  relay_status: boolean
}

export interface Prediction {
  fault_type: string
  fault_index: number
  confidence: number
  is_fault: boolean
  power: number
  efficiency: number
  timestamp: string
  recommendation?: string
  decision_state?: string
  probability_method?: string
  // Stabilized / enriched fields (v4.1+)
  stabilized_fault_type?: string
  stabilized_confidence?: number
  explanation?: string
  recommended_solution?: string
  final_assessment?: string
  weather_adjusted_interpretation?: string
  expected_generation_context?: string
  day_night_status?: string
  weather_summary?: string
  action_urgency?: string
  suppress_alarm?: boolean
  monitoring_state?: string
  weather_interpretation?: {
    final_interpretation?: string
    likely_weather_related?: boolean
    action_urgency?: string
    weather_summary?: string
    is_day?: boolean
    period?: string
  } | null
}

export interface HistoryEntry {
  time: string
  voltage: number | null
  current: number | null
  temperature: number | null
  light: number | null
  humidity: number | null
  thermistor: number | null
  power: number | null
  efficiency: number | null
  irradiance: number | null
  expected: number | null
  relay: boolean
  fault: string
}

export interface WeatherCurrent {
  temperature: number | null
  feels_like: number | null
  humidity: number | null
  cloud_cover: number | null
  wind_speed: number | null
  precipitation: number | null
  weather_code: number | null
  description: string
  is_day_api: boolean
}

export interface DayNight {
  is_day: boolean
  period: string
  sunrise: string
  sunset: string
}

export interface WeatherForecastEntry {
  time: string
  temperature: number | null
  description: string
  cloud_cover: number | null
  precipitation_probability: number | null
}

export interface WeatherData {
  is_available: boolean
  location: string
  current: WeatherCurrent | null
  day_night: DayNight
  weather_context: {
    expected_output: string
    reason: string
    suppress_low_output_alarm: boolean
    weather_summary: string
    is_rain: boolean
  }
  forecast: WeatherForecastEntry[]
  fetched_at: string
  error?: string
}

export interface StationState {
  sensorData: SensorData | null
  prediction: Prediction | null
  history: HistoryEntry[]
  faultCounts: Record<string, number>
  lastUpdate: Date
}

export interface ManualSimulatorValues {
  voltage: number
  current: number
  temperature: number
  light_intensity: number
  humidity: number
  thermistor_temp: number
}

export interface RelayCommandStatus {
  time: string
  station: number
  command: string
  status: string
}

export interface CsvStats {
  file_size: string
  row_count: number
}

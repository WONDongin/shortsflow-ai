// 영상 작업 화면의 공통 선형 아이콘
const paths = {
  film: 'M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z M8 4v16m8-16v16M3 9h5m-5 6h5m8-6h5m-5 6h5',
  play: 'M9 6.5 18 12l-9 5.5v-11Z',
  upload: 'M12 16V4m-4 4 4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3',
  download: 'M12 4v12m-4-4 4 4 4-4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3',
  search: 'M19.5 19.5 16 16M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z',
  arrow: 'M4 12h15m-6-6 6 6-6 6',
  audio: 'M3 12h2m3-5v10m4-13v16m4-13v10m3-5h2',
  text: 'M5 5h14v14H5zM8 9h8m-8 3h8m-8 3h4',
  frame: 'M9 4H5a1 1 0 0 0-1 1v4m11-5h4a1 1 0 0 1 1 1v4M4 15v4a1 1 0 0 0 1 1h4m11-5v4a1 1 0 0 1-1 1h-4M8 15l3-4 2 2 2-3 2 5H8Z',
  check: 'm5 12 4 4L19 6',
  alert: 'M12 8v5m0 3h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  spark: 'M12 2.5 14.5 9.5 21.5 12l-7 2.5L12 21.5l-2.5-7L2.5 12l7-2.5L12 2.5Z',
} as const

export function Icon({ name, className }: { name: keyof typeof paths; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={paths[name]} />
    </svg>
  )
}

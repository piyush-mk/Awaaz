import { Route, Routes } from 'react-router-dom'
import KhataList from '../../components/app/khata/KhataList'
import KhataDetail from '../../components/app/khata/KhataDetail'

export default function Khata() {
  return (
    <Routes>
      <Route index element={<KhataList />} />
      <Route path=":id" element={<KhataDetail />} />
    </Routes>
  )
}

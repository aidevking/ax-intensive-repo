import NavBar from './NavBar';
import './styles.css';

export const metadata = {
  title: 'App Review Analyze',
  description: '앱 리뷰와 분석 결과를 app/review/review_analysis 스키마로 조회합니다.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <NavBar />
        {children}
      </body>
    </html>
  );
}

var { useState, useEffect } = React;
var { BrowserRouter, Switch, Route, Redirect } = ReactRouterDOM;

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);

  useEffect(() => {
    const checkSession = async () => {
      try {
        const response = await fetch('/me', { credentials: 'include' });
        if (response.ok) {
          const data = await response.json();
          setIsAuthenticated(true);
          setUser(data.email);
        } else {
          setIsAuthenticated(false);
          setUser(null);
        }
      } catch (err) {
        setIsAuthenticated(false);
      } finally {
        setCheckingAuth(false);
      }
    };
    checkSession();
  }, []);

  const handleLoginSuccess = (email) => {
    setIsAuthenticated(true);
    setUser(email);
  };

  const handleLogout = async () => {
    await fetch('/logout', { method: 'POST', credentials: 'include' });
    setIsAuthenticated(false);
    setUser(null);
  };

  if (checkingAuth) return <div style={{ padding: '20px' }}>Loading...</div>;

  return (
    <BrowserRouter>
      <header style={{ padding: '15px 20px', backgroundColor: '#333', color: '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>Transit Incident Manager</h2>
        <div>
          {isAuthenticated ? (
            <div>
              <span style={{ marginRight: '15px' }}>User: <strong>{user}</strong></span>
              <button onClick={handleLogout} style={{ padding: '6px 12px' }}>Logout</button>
            </div>
          ) : (
            <span style={{ color: '#aaa' }}>Not Authenticated</span>
          )}
        </div>
      </header>

      <main style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
        <Switch>
          <Route exact path="/" render={() => <Home isAuthenticated={isAuthenticated} />} />
          <Route path="/login" render={() => (isAuthenticated ? <Redirect to="/" /> : <Login onLoginSuccess={handleLoginSuccess} />)} />
          <Route path="/create" render={() => (isAuthenticated ? <CreateRecord /> : <Redirect to="/login" />)} />
          <Route path="/update" render={() => (isAuthenticated ? <UpdateRecord /> : <Redirect to="/login" />)} />
          <Route path="/delete" render={() => (isAuthenticated ? <DeleteRecord /> : <Redirect to="/login" />)} />
        </Switch>
      </main>
    </BrowserRouter>
  );
}

window.addEventListener('load', () => {
  ReactDOM.render(<App />, document.getElementById('root'));
});

ReactDOM.render(<App />, document.getElementById('root'));
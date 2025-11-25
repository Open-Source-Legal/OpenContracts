import { Menu, Icon } from "semantic-ui-react";
import { Link } from "react-router-dom";
import styled from "styled-components";
import Dropdown from "../common/Dropdown";

import logo from "../../assets/images/os_legal_128.png";
import user_logo from "../../assets/icons/noun-person-113116-FFFFFF.png";
import { showExportModal } from "../../graphql/cache";
import "./MobileNavMenu.css";
import { useNavMenu } from "./useNavMenu";

const MiniImage = styled.img`
  width: 35px;
  height: 35px;
  margin-right: 1.5em;
  object-fit: contain;
`;

const AvatarImage = styled.img`
  width: 2em;
  height: 2em;
  border-radius: 50%;
  object-fit: cover;
  display: inline-block;
  vertical-align: middle;
`;

export const MobileNavMenu = () => {
  const {
    user,
    isLoading,
    REACT_APP_USE_AUTH0,
    REACT_APP_AUDIENCE,
    public_header_items,
    private_header_items,
    show_export_modal,
    pathname,
    isActive,
    requestLogout,
    loginWithPopup,
    loginWithRedirect,
  } = useNavMenu();

  // Note: CentralRouteManager automatically clears openedCorpus/openedDocument when navigating
  // No need to manually clear on menu clicks

  const items = public_header_items.map((item) => (
    <Dropdown.Item
      id={item.id}
      className="uninvert_me"
      name={item.title}
      active={isActive(item.route)}
      key={`${item.title}`}
    >
      <Link to={item.route}>{item.title}</Link>
    </Dropdown.Item>
  ));

  const private_items = private_header_items.map((item) => (
    <Dropdown.Item
      id={item.id}
      className="uninvert_me"
      name={item.title}
      active={isActive(item.route)}
      key={`${item.title}`}
    >
      <Link to={item.route}>{item.title}</Link>
    </Dropdown.Item>
  ));

  if (REACT_APP_USE_AUTH0) {
    return (
      <Menu
        fluid
        inverted
        attached
        style={{
          marginBottom: "0px",
          position: "sticky",
          top: 0,
          zIndex: 1000, // Above all other content including ChatContainer (z-index: 10) and ChatNavigationHeader (z-index: 100)
        }}
      >
        <Menu.Menu position="left">
          <Menu.Item>
            <MiniImage src={logo} alt="Open Contracts Logo" />
            <Dropdown
              id="MobileMenuDropdown"
              item
              simple
              text="Open Contracts"
              dark
            >
              <Dropdown.Menu>
                {user ? [...items, ...private_items] : items}
                {user && (user as any).isSuperuser && (
                  <Dropdown.Item
                    id="admin_badges_menu_button_mobile"
                    className="uninvert_me"
                    name="Badge Management"
                    active={isActive("/admin/badges")}
                  >
                    <Link to="/admin/badges">Badge Management</Link>
                  </Dropdown.Item>
                )}
              </Dropdown.Menu>
            </Dropdown>
          </Menu.Item>
        </Menu.Menu>

        <Menu.Menu position="right">
          {!isLoading && user ? (
            <>
              <Menu.Item>
                <AvatarImage src={user_logo} alt="User Avatar" />
                <Dropdown
                  item
                  simple
                  icon={<Icon style={{ marginLeft: "5px" }} name="dropdown" />}
                  text={` ${user?.name ? user.name : user.username}`}
                  style={{ margin: "0px", padding: "0px" }}
                  header="Logout"
                  dark
                >
                  <Dropdown.Menu>
                    <Dropdown.Item
                      text="Exports"
                      onClick={() => showExportModal(!show_export_modal)}
                      icon={<Icon name="download" />}
                    />
                    <Dropdown.Item
                      text="Logout"
                      onClick={() => requestLogout()}
                      icon={<Icon name="log out" />}
                    />
                    {/* <Dropdown.Item
                                            text='Settings'
                                            onClick={() => console.log("Do nothing yet...")}
                                            icon={<Icon name='settings'/>}
                                        /> */}
                  </Dropdown.Menu>
                </Dropdown>
              </Menu.Item>
            </>
          ) : (
            <Menu.Item
              onClick={async () => {
                try {
                  await loginWithPopup({
                    authorizationParams: {
                      audience: REACT_APP_AUDIENCE || undefined,
                      scope: "openid profile email",
                      redirect_uri: window.location.origin,
                    },
                  });
                } catch (e) {
                  await loginWithRedirect({
                    authorizationParams: {
                      audience: REACT_APP_AUDIENCE || undefined,
                      scope: "openid profile email",
                    },
                  });
                }
              }}
            >
              Login
            </Menu.Item>
          )}
        </Menu.Menu>
      </Menu>
    );
  } else {
    return (
      <Menu
        fluid
        inverted
        attached
        style={{
          marginBottom: "0px",
          position: "sticky",
          top: 0,
          zIndex: 1000, // Above all other content including ChatContainer (z-index: 10) and ChatNavigationHeader (z-index: 100)
        }}
      >
        <Menu.Menu position="left">
          <Menu.Item>
            <MiniImage src={logo} alt="Open Contracts Logo" />
            <Dropdown
              id="MobileMenuDropdown"
              item
              simple
              text="Open Contracts"
              dark
            >
              <Dropdown.Menu>
                {user ? [...items, ...private_items] : items}
                {user && (user as any).isSuperuser && (
                  <Dropdown.Item
                    id="admin_badges_menu_button_mobile"
                    className="uninvert_me"
                    name="Badge Management"
                    active={isActive("/admin/badges")}
                  >
                    <Link to="/admin/badges">Badge Management</Link>
                  </Dropdown.Item>
                )}
              </Dropdown.Menu>
            </Dropdown>
          </Menu.Item>
        </Menu.Menu>

        <Menu.Menu position="right">
          {user ? (
            <>
              <Menu.Item>
                <AvatarImage src={user_logo} alt="User Avatar" />
                <Dropdown
                  item
                  simple
                  icon={<Icon style={{ marginLeft: "5px" }} name="dropdown" />}
                  text={` ${user?.name ? user.name : user.username}`}
                  style={{ margin: "0px", padding: "0px" }}
                  header="Logout"
                  dark
                >
                  <Dropdown.Menu>
                    <Dropdown.Item
                      text="Exports"
                      onClick={() => showExportModal(!show_export_modal)}
                      icon={<Icon name="download" />}
                    />
                    <Dropdown.Item
                      text="Logout"
                      onClick={() => requestLogout()}
                      icon={<Icon name="log out" />}
                    />
                    {/* <Dropdown.Item
                                            text='Settings'
                                            onClick={() => console.log("Do nothing yet...")}
                                            icon={<Icon name='settings'/>}
                                        /> */}
                  </Dropdown.Menu>
                </Dropdown>
              </Menu.Item>
            </>
          ) : (
            <Menu.Item
              id="login_nav_button"
              name="Login"
              active={pathname === "/login"}
              key="login_nav_button"
            >
              <Link to="/login">Login</Link>
            </Menu.Item>
          )}
        </Menu.Menu>
      </Menu>
    );
  }
};

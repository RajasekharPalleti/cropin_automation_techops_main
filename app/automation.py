import re
from playwright.async_api import async_playwright

async def change_password_via_portal(admin_username, admin_password, new_password, tenant, contact_number, update_callback=None):
    """
    Automates the Keycloak Admin Console to change a user's password.
    """
    async def report_step(msg):
        if update_callback:
            await update_callback(msg)

    async with async_playwright() as p:
        # Launch browser in headful mode for debugging
        browser = await p.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        try:
            await report_step("Navigating to auth portal...")
            # 1. Go to auth portal
            await page.goto("https://sso.sg.cropin.in/auth/")

            # 2. Click "Administration Console"
            await report_step("Loading Administration Console...")
            await page.get_by_text(re.compile("Administration Console", re.IGNORECASE)).click()

            # 3. Wait for login and fill credentials
            await report_step("Entering admin credentials...")
            # Use label text or placeholder "Username or email" and "Password"
            username_field = page.locator("input[name='username']")
            await username_field.wait_for(state="visible", timeout=10000)
            await username_field.fill(admin_username)
            
            password_field = page.locator("input[name='password']")
            await password_field.fill(admin_password)
            
            # Click "Log In" button
            await page.locator("input[value='Log In'], button:has-text('log in')").first.click()

            # Wait for login to complete and the page to load
            await report_step("Waiting for login to complete and Realms page to load...")
            await page.wait_for_load_state("load")

            # 4. Search for the tenant on the Realms page
            await report_step(f"Searching for tenant '{tenant}'...")
            
            # Since there is no search box, find the exact link in the table and click it.
            tenant_link = page.locator(f"a[href='#/realms/{tenant}' i]").first
            await tenant_link.wait_for(state="visible", timeout=15000)
            
            await report_step(f"Selecting tenant '{tenant}'...")
            await tenant_link.click()

            # Add a small delay for Angular rendering
            await page.wait_for_timeout(2000)

            # 5. Click on 'Users' in the side panel
            await report_step("Opening Users panel...")
            # Use exact href match for the Users link based on HTML structure
            users_link = page.locator(f"a[href='#/realms/{tenant}/users' i]").first
            await users_link.wait_for(state="visible", timeout=15000)
            await users_link.click()

            await page.wait_for_timeout(2000)

            # 6. Enter mobile number in search box and hit Enter
            await report_step(f"Searching for contact number '{contact_number}'...")
            # Keycloak users search input (matching data-ng-model or placeholder)
            user_search = page.locator("input[data-ng-model='query.search'], input[placeholder='Search...']").first
            await user_search.wait_for(state="visible", timeout=10000)
            await user_search.fill(contact_number)
            await user_search.press("Enter")
            
            # Allow time for search results to load
            await page.wait_for_timeout(2000)

            # 7. Find the row and click Edit in Actions
            await report_step("Opening user settings (Edit)...")
            edit_btn = page.locator("text='Edit'").first
            await edit_btn.wait_for(state="visible", timeout=10000)
            await edit_btn.click()

            await page.wait_for_timeout(2000)

            # 8. Click on Credentials tab
            await report_step("Opening Credentials tab...")
            credentials_tab = page.locator("ul.nav-tabs li a:has-text('Credentials'), a:text-is('Credentials')").first
            await credentials_tab.wait_for(state="visible", timeout=10000)
            await credentials_tab.click()

            await page.wait_for_timeout(2000)

            # 9. Enter password in both "New Password" and "Password Confirmation"
            await report_step("Submitting new password...")
            
            # Keycloak 7.x credential fields use id 'newPas' and 'confirmPas'
            new_pwd_input = page.locator("input#newPas, input[data-ng-model='password']").first
            confirm_pwd_input = page.locator("input#confirmPas, input[data-ng-model='confirmPassword']").first

            await new_pwd_input.wait_for(state="visible", timeout=5000)
            await new_pwd_input.fill(new_password)
            await confirm_pwd_input.fill(new_password)

            # 10. Click the Reset Password or Save button again to submit
            save_btn = page.locator("button:has-text('Reset Password'), button:has-text('Save'), button:has-text('Change')").first
            await save_btn.click()

            # 11. Change password modal will populate. click on "Change password" button in modal.
            await page.wait_for_timeout(1000)
            modal_change_btn = page.locator("button:has-text('Change password'), button:has-text('Change')").first
            if await modal_change_btn.is_visible():
                await modal_change_btn.click()

            # Verify it's done by waiting for the success toast/message
            await report_step("Waiting for success confirmation...")
            success_toast = page.locator(".alert-success, div.alert:has-text('password')").first
            await success_toast.wait_for(state="visible", timeout=10000)
            
            await report_step("Password successfully changed!")
            return {"status": "success", "message": "Password changed successfully."}

        except Exception as e:
            # Save screenshot for debugging
            import time
            timestamp = int(time.time())
            screenshot_path = f"/tmp/playwright_error_{timestamp}.png"
            await page.screenshot(path=screenshot_path)
            raise Exception(f"Playwright automation failed: {str(e)}. (Screenshot saved to {screenshot_path})")
        finally:
            await browser.close()

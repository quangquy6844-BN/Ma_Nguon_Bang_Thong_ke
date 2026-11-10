
document.addEventListener("DOMContentLoaded", function () {

    // Mở menu trên điện thoại
    const menuToggle = document.getElementById("menuToggle");
    const sidebar = document.getElementById("sidebar");

    if (menuToggle && sidebar) {
        menuToggle.addEventListener("click", function () {
            sidebar.classList.toggle("open");
        });
    }


    // Tìm kiếm doanh thu
    const searchInput = document.getElementById("searchInput");
    const revenueTable = document.getElementById("revenueTable");

    if (searchInput && revenueTable) {

        searchInput.addEventListener("input", function () {

            const keyword = this.value.toLowerCase();

            const rows = revenueTable.querySelectorAll("tbody tr");

            rows.forEach(function (row) {

                const content = row.innerText.toLowerCase();

                row.style.display = content.includes(keyword)
                    ? ""
                    : "none";

            });

        });

    }


    // Thêm doanh thu (hiện chỉ thêm vào bảng trên trình duyệt)
    const revenueForm = document.getElementById("revenueForm");

    if (revenueForm) {

        revenueForm.addEventListener("submit", function (event) {

            event.preventDefault();

            const date = document.getElementById("revenueDate").value;
            const receipt = document.getElementById("receipt").value;
            const description = document.getElementById("description").value;
            const category = document.getElementById("category").value;
            const amount = Number(document.getElementById("amount").value);

            const row = document.createElement("tr");

            const dateText = date.split("-").reverse().join("/");
            const amountText = amount.toLocaleString("vi-VN") + " đ";

            const values = [
                dateText,
                receipt || "—",
                description,
                category,
                amountText
            ];

            values.forEach(function (value, index) {

                const cell = document.createElement("td");

                cell.textContent = value;

                if (index === 4) {
                    cell.classList.add("text-end");
                }

                row.appendChild(cell);

            });

            revenueTable.querySelector("tbody").prepend(row);

            bootstrap.Modal.getInstance(
                document.getElementById("revenueModal")
            ).hide();

            revenueForm.reset();

            alert("Thêm doanh thu thành công!");

        });

    }

});

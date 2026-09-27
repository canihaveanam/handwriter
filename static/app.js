const fieldNames = [
    "病区",
    "姓名",
    "床号",
    "住院号"
];

let layoutEditing = false;
let renderedPreview = false;
let savedImageLayout = {};

let currentTaskId = null;
let currentPageCount = 0;

let currentBackgroundId = null;
let currentBackgroundUrl = "/base.jpg";


let currentTemplateId = null;
let currentTemplateName = "";
let defaultTemplateId = null;


/*
    只要用户修改了内容或布局，
    上一次生成的 ZIP 就视为过期。
    必须重新点击“预览生成效果”。
*/
function invalidateGeneratedTask(){

    currentTaskId = null;
    currentPageCount = 0;

    const button =
        document.getElementById(
            "downloadAllImages"
        );

    if(button){
        button.disabled = true;
    }

}


/* =========================================================
   自定义背景
========================================================= */

function setBackgroundStatus(message){
    const el = document.getElementById("backgroundStatus");
    if(el){
        el.textContent = message || "";
    }
}

function showBackgroundOnCanvas(url){
    const canvasImage = document.getElementById("canvasImage");
    if(!canvasImage){
        return;
    }

    if(renderedPreview){
        showEditorCanvas();
    }

    canvasImage.onload = function(){
        if(Object.keys(savedImageLayout).length > 0){
            applyImagePixelLayout(savedImageLayout);
        }
        updateCanvasText();
        canvasImage.onload = null;
    };

    canvasImage.src = url + (url.includes("?") ? "&" : "?") + "t=" + Date.now();
}

async function uploadCustomBackground(file){
    if(!file){
        return;
    }

    const allowedTypes = ["image/jpeg", "image/png"];
    const lowerName = file.name.toLowerCase();
    const extensionOk = lowerName.endsWith(".jpg")
        || lowerName.endsWith(".jpeg")
        || lowerName.endsWith(".png");

    if(!allowedTypes.includes(file.type) && !extensionOk){
        alert("背景只支持 JPG、JPEG、PNG");
        document.getElementById("backgroundFile").value = "";
        return;
    }

    if(file.size > 15 * 1024 * 1024){
        alert("背景图片不能超过 15 MB");
        document.getElementById("backgroundFile").value = "";
        return;
    }

    const radio = document.getElementById("customBackgroundRadio");
    if(radio){
        radio.checked = true;
    }

    setBackgroundStatus("正在上传并处理背景...");

    const formData = new FormData();
    formData.append("background", file);

    try{
        const res = await fetch("/upload_background", {
            method:"POST",
            body:formData
        });

        const data = await res.json();
        if(!res.ok || !data.success){
            throw new Error(data.error || "背景上传失败");
        }

        currentBackgroundId = data.background_id;
        currentBackgroundUrl = data.preview_url;
        invalidateGeneratedTask();
        showBackgroundOnCanvas(currentBackgroundUrl);

        setBackgroundStatus(
            `当前：自定义背景 ${file.name}（已适配为 ${data.width}×${data.height}）`
        );
    }
    catch(e){
        console.error("背景上传失败", e);
        alert("背景上传失败：" + e.message);
        useDefaultBackground();
    }
}

function useDefaultBackground(){
    currentBackgroundId = null;
    currentBackgroundUrl = "/base.jpg";

    const defaultRadio = document.querySelector(
        'input[name="backgroundSource"][value="default"]'
    );
    if(defaultRadio){
        defaultRadio.checked = true;
    }

    const fileInput = document.getElementById("backgroundFile");
    if(fileInput){
        fileInput.value = "";
    }

    invalidateGeneratedTask();
    showBackgroundOnCanvas(currentBackgroundUrl);
    setBackgroundStatus("当前：默认背景");
}

/* =========================================================
   模板阶段1：正文“待替换区域”
========================================================= */

function getEditor(){

    return document.getElementById(
        "text_content"
    );

}


function getEditorPlainText(){

    const editor = getEditor();

    if(!editor){
        return "";
    }

    /*
        innerText 会把 contenteditable 中的换行转换成普通文本换行，
        Pillow 只接收这里的纯文字，不会收到黄色背景或 HTML。
    */
    return editor.innerText
        .replace(/\r\n/g, "\n");

}


function getClosestTemplateSlot(node){

    if(!node){
        return null;
    }

    let element =
        node.nodeType === Node.ELEMENT_NODE
        ? node
        : node.parentElement;

    if(!element){
        return null;
    }

    return element.closest(
        ".template-slot"
    );

}



function markSelectedText(){

    const editor =
        getEditor();

    const selection =
        window.getSelection();

    if(
        !editor
        ||
        !selection
        ||
        selection.rangeCount === 0
        ||
        selection.isCollapsed
    ){
        alert(
            "请先在正文中选择要标记的文字"
        );

        return;
    }

    const range =
        selection.getRangeAt(0);

    const commonNode =
        range.commonAncestorContainer;

    const commonElement =
        commonNode.nodeType
        === Node.ELEMENT_NODE
        ? commonNode
        : commonNode.parentElement;

    if(
        !commonElement
        ||
        (
            commonElement !== editor
            &&
            !editor.contains(
                commonElement
            )
        )
    ){
        alert(
            "只能标记正文中的文字"
        );

        return;
    }

    const selectedText =
        range.toString();

    if(
        !selectedText
        ||
        !selectedText.trim()
    ){
        alert(
            "请选择实际文字，不要只选择空格或换行"
        );

        return;
    }

    /*
        如果选择范围里已经包含黄色区域，
        阶段1先不允许嵌套标记，避免结构变复杂。
    */
    const fragment =
        range.cloneContents();

    if(
        fragment.querySelector
        &&
        fragment.querySelector(
            ".template-slot"
        )
    ){
        alert(
            "选择范围中已经包含标记区域"
        );

        return;
    }

    const slot =
        document.createElement(
            "span"
        );

    slot.className =
        "template-slot";

    slot.dataset.originalText =
        selectedText;

    slot.dataset.slotId =
        (
            window.crypto
            &&
            crypto.randomUUID
        )
        ? crypto.randomUUID()
        : (
            "slot_"
            + Date.now()
            + "_"
            + Math.random()
                .toString(16)
                .slice(2)
        );

    /*
        extractContents + insertNode 比 surroundContents 更稳：
        即使选择跨过了简单的文本节点，也能正常包装。
    */
    const content =
        range.extractContents();

    slot.appendChild(
        content
    );

    range.insertNode(
        slot
    );

    selection.removeAllRanges();

    /*
        标记完成后直接选中黄色区域，
        用户可以马上 Ctrl+C / Ctrl+V 测试。
    */
    const newRange =
        document.createRange();

    newRange.selectNodeContents(
        slot
    );

    selection.addRange(
        newRange
    );


}


function selectWholeTemplateSlot(
    slot
){

    if(!slot){
        return;
    }

    const selection =
        window.getSelection();

    const range =
        document.createRange();

    range.selectNodeContents(
        slot
    );

    selection.removeAllRanges();

    selection.addRange(
        range
    );

}


/*
    一旦黄色区域中的文字发生变化，
    就把 span 拆掉，只留下普通文本。

    所以：
    原来：
        <span class="template-slot">右膝疼痛3个月</span>

    用户粘贴以后：
        左膝疼痛2周

    黄色和 HTML 标记都会自动消失。
*/
function clearChangedTemplateSlots(){

    const editor =
        getEditor();

    if(!editor){
        return;
    }

    const changedSlots =
        [];

    editor
        .querySelectorAll(
            ".template-slot"
        )
        .forEach(
            slot => {

                const original =
                    slot.dataset.originalText
                    ?? "";

                if(
                    slot.textContent
                    !== original
                ){
                    changedSlots.push(
                        slot
                    );
                }

            }
        );

    changedSlots.forEach(
        slot => {

            const textNode =
                document.createTextNode(
                    slot.textContent
                );

            slot.replaceWith(
                textNode
            );

        }
    );

    if(changedSlots.length){

        editor.normalize();

    }


}


function initTemplateEditor(){

    const editor =
        getEditor();

    if(!editor){
        return;
    }

    /*
        点击黄色文字时自动选中整块。
        下一步只需要 Ctrl+V 即可覆盖。
    */
    editor.addEventListener(
        "click",
        function(e){

            const slot =
                getClosestTemplateSlot(
                    e.target
                );

            if(!slot){
                return;
            }

            selectWholeTemplateSlot(
                slot
            );

        }
    );


    /*
        粘贴 / 输入改变黄色区域后：
        自动去掉黄色。

        使用 input 而不是只监听 paste，
        所以直接键盘输入替换同样有效。
    */
    editor.addEventListener(
        "input",
        function(){

            clearChangedTemplateSlots();

        }
    );


    /*
        从病历系统复制过来的内容一律按纯文本粘贴，
        防止把 Word / 网页颜色、字体、表格样式一起带进模板。
    */
    editor.addEventListener(
        "paste",
        function(e){

            e.preventDefault();

            const text =
                e.clipboardData
                    .getData(
                        "text/plain"
                    );

            const selection =
                window.getSelection();

            if(
                !selection
                ||
                selection.rangeCount === 0
            ){
                return;
            }

            const range =
                selection.getRangeAt(0);

            range.deleteContents();

            const node =
                document.createTextNode(
                    text
                );

            range.insertNode(
                node
            );

            range.setStartAfter(
                node
            );

            range.collapse(
                true
            );

            selection.removeAllRanges();

            selection.addRange(
                range
            );


            editor.dispatchEvent(
                new InputEvent(
                    "input",
                    {
                        bubbles:true,
                        inputType:
                            "insertFromPaste",
                        data:text
                    }
                )
            );

        }
    );


}


/* =========================================================
   模板阶段2：保存 / 加载完整模板
========================================================= */

function setTemplateStatus(
    message
){

    const el =
        document.getElementById(
            "templateStatus"
        );

    if(el){
        el.textContent =
            message || "";
    }

}


function getTemplateUiSettings(){

    const result = {
        font:
            document
                .getElementById(
                    "font"
                )
                .value
    };

    settingsConfig.forEach(
        item => {

            const el =
                document.getElementById(
                    item[0]
                );

            if(el){

                result[item[0]] =
                    Number(
                        el.value
                    );

            }

        }
    );

    return result;

}


function applyTemplateUiSettings(
    settings
){

    if(!settings){
        return;
    }

    if(
        settings.font
        !== undefined
    ){

        const fontSelect =
            document.getElementById(
                "font"
            );

        /*
            模板里保存的字体如果目前仍存在，
            就恢复它。
        */
        const exists =
            Array.from(
                fontSelect.options
            )
            .some(
                option =>
                    option.value
                    === settings.font
            );

        if(exists){

            fontSelect.value =
                settings.font;

        }

    }


    settingsConfig.forEach(
        item => {

            if(
                settings[item[0]]
                === undefined
            ){
                return;
            }

            const el =
                document.getElementById(
                    item[0]
                );

            if(el){

                el.value =
                    settings[item[0]];

            }

        }
    );


    applyPreviewTextSettings();

}


function getTemplatePayload(
    name,
    templateId=null
){

    if(
        !renderedPreview
    ){

        savedImageLayout =
            getImagePixelLayout();

    }

    return {

        id:
            templateId,

        name:
            name,

        fields:
            getFields(),

        settings:
            getTemplateUiSettings(),

        boxes:
            savedImageLayout,

        /*
            这里保存 innerHTML，
            所以黄色 template-slot 会被完整保存。
        */
        body_html:
            getEditor().innerHTML,

        /*
            顺便保存纯文本，方便以后调试、搜索或升级格式。
        */
        body_text:
            getEditorPlainText()

    };

}


async function loadTemplateList(
    selectedId=null,
    autoLoadDefault=false
){

    const select =
        document.getElementById(
            "templateSelect"
        );

    try{

        const res =
            await fetch(
                "/api/templates"
            );

        const data =
            await res.json();

        if(!data.success){

            throw new Error(
                data.error
                || "模板列表加载失败"
            );

        }


        defaultTemplateId =
            data.default_template_id
            || null;


        select.innerHTML =
            `<option value="">
                请选择模板
            </option>`;


        data.templates.forEach(
            item => {

                const option =
                    document.createElement(
                        "option"
                    );

                option.value =
                    item.id;

                option.textContent =
                    (
                        item.name
                        +
                        (
                            item.id
                            === defaultTemplateId
                            ? "（默认）"
                            : ""
                        )
                    );

                select.appendChild(
                    option
                );

            }
        );


        let targetId =
            selectedId
            || currentTemplateId;


        /*
            只有程序初始化时才自动打开默认模板。
            保存、另存为、设置默认等刷新列表时，
            不会突然重新加载正文。
        */
        if(
            autoLoadDefault
            &&
            defaultTemplateId
        ){

            targetId =
                defaultTemplateId;

        }


        if(targetId){

            select.value =
                targetId;

        }


        if(
            autoLoadDefault
            &&
            defaultTemplateId
            &&
            select.value
            === defaultTemplateId
        ){

            await loadSelectedTemplate();

        }

    }
    catch(e){

        console.error(
            "模板列表加载失败",
            e
        );

        setTemplateStatus(
            "模板列表加载失败"
        );

    }

}

async function loadSelectedTemplate(){

    const select =
        document.getElementById(
            "templateSelect"
        );

    const templateId =
        select.value;

    if(!templateId){
        return;
    }


    try{

        setTemplateStatus(
            "正在加载模板..."
        );


        const res =
            await fetch(
                "/api/templates/"
                + encodeURIComponent(
                    templateId
                )
            );

        const data =
            await res.json();


        if(!data.success){

            throw new Error(
                data.error
                || "模板加载失败"
            );

        }


        /*
            如果正在看 Pillow 多页预览，
            先回到可编辑画布。
        */
        if(renderedPreview){

            showEditorCanvas();

        }


        /*
            如果恰好处在布局编辑状态，
            先结束编辑状态，避免新模板载入后仍显示蓝框。
        */
        if(layoutEditing){

            layoutEditing =
                false;

            document
                .getElementById(
                    "previewFrame"
                )
                .classList.remove(
                    "editing"
                );

            document
                .getElementById(
                    "layoutEditBtn"
                )
                .textContent =
                "编辑布局";

        }


        const tpl =
            data.template;


        fieldNames.forEach(
            name => {

                const input =
                    document.getElementById(
                        name
                    );

                if(input){

                    input.value =
                        (
                            tpl.fields
                            &&
                            tpl.fields[name]
                            !== undefined
                        )
                        ? tpl.fields[name]
                        : "";

                }

            }
        );


        const editor =
            getEditor();

        if(
            tpl.body_html
            !== undefined
        ){

            /*
                body_html 是我们自己保存的本地模板内容。
                黄色区域及其 data-original-text 会恢复。
            */
            editor.innerHTML =
                tpl.body_html;

        }
        else{

            editor.textContent =
                tpl.body_text
                || "";

        }


        applyTemplateUiSettings(
            tpl.settings
            || {}
        );


        if(
            tpl.boxes
            &&
            Object.keys(
                tpl.boxes
            ).length > 0
        ){

            savedImageLayout =
                tpl.boxes;

            applyImagePixelLayout(
                savedImageLayout
            );

        }


        currentTemplateId =
            tpl.id;

        currentTemplateName =
            tpl.name;


        invalidateGeneratedTask();

        updateCanvasText();


        setTemplateStatus(
            "已加载模板："
            + currentTemplateName
        );

    }
    catch(e){

        console.error(
            "模板加载失败",
            e
        );

        alert(
            "模板加载失败："
            + e.message
        );

        setTemplateStatus(
            "模板加载失败"
        );

    }

}


async function saveTemplateRequest(
    templateId,
    templateName
){

    if(layoutEditing){

        alert(
            "请先点击“完成”保存当前布局"
        );

        return;
    }


    const name =
        (
            templateName
            || ""
        ).trim();

    if(!name){

        alert(
            "模板名称不能为空"
        );

        return;
    }


    /*
        多页真实预览状态下，savedImageLayout 已经保存了
        最后一次完成编辑时的原图像素坐标，不需要切回画布。
    */
    const payload =
        getTemplatePayload(
            name,
            templateId
        );


    try{

        setTemplateStatus(
            "正在保存模板..."
        );


        const res =
            await fetch(
                "/api/templates",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(
                            payload
                        )
                }
            );


        const data =
            await res.json();


        if(!data.success){

            throw new Error(
                data.error
                || "模板保存失败"
            );

        }


        currentTemplateId =
            data.template.id;

        currentTemplateName =
            data.template.name;


        await loadTemplateList(
            currentTemplateId,
            false
        );


        setTemplateStatus(
            "已保存模板："
            + currentTemplateName
        );

    }
    catch(e){

        console.error(
            "保存模板失败",
            e
        );

        alert(
            "保存模板失败："
            + e.message
        );

        setTemplateStatus(
            "模板保存失败"
        );

    }

}


async function saveTemplate(){

    let name =
        currentTemplateName;


    if(
        !currentTemplateId
        ||
        !name
    ){

        name =
            prompt(
                "请输入模板名称",
                ""
            );

        if(name === null){
            return;
        }

    }


    await saveTemplateRequest(
        currentTemplateId,
        name
    );

}


async function saveTemplateAs(){

    const defaultName =
        currentTemplateName
        ? currentTemplateName + " 副本"
        : "";


    const name =
        prompt(
            "另存为模板名称",
            defaultName
        );


    if(name === null){
        return;
    }


    await saveTemplateRequest(
        null,
        name
    );

}



async function setDefaultTemplate(){

    const select =
        document.getElementById(
            "templateSelect"
        );

    const templateId =
        select.value
        || currentTemplateId;

    if(!templateId){

        alert(
            "请先选择或保存一个模板"
        );

        return;
    }


    try{

        setTemplateStatus(
            "正在设置默认模板..."
        );


        const res =
            await fetch(
                "/api/templates/default",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            id:
                                templateId
                        })
                }
            );


        const data =
            await res.json();


        if(!data.success){

            throw new Error(
                data.error
                || "设置默认模板失败"
            );

        }


        defaultTemplateId =
            templateId;


        await loadTemplateList(
            templateId,
            false
        );


        const selectedOption =
            document
                .getElementById(
                    "templateSelect"
                )
                .selectedOptions[0];


        const displayName =
            currentTemplateId
            === templateId
            ? currentTemplateName
            : (
                selectedOption
                ? selectedOption.textContent
                    .replace(
                        "（默认）",
                        ""
                    )
                    .trim()
                : "当前模板"
            );


        setTemplateStatus(
            "已设为默认模板："
            + displayName
        );

    }
    catch(e){

        console.error(
            "设置默认模板失败",
            e
        );

        alert(
            "设置默认模板失败："
            + e.message
        );

        setTemplateStatus(
            "设置默认模板失败"
        );

    }

}


async function deleteTemplate(){

    const select =
        document.getElementById(
            "templateSelect"
        );

    const templateId =
        select.value;

    if(!templateId){

        alert(
            "请先从下拉框选择要删除的模板"
        );

        return;
    }


    const option =
        select.selectedOptions[0];

    const templateName =
        option
        ? option.textContent
            .replace(
                "（默认）",
                ""
            )
            .trim()
        : "当前模板";


    if(
        !confirm(
            "确定删除模板“"
            + templateName
            + "”吗？"
            + "\n\n删除后模板文件会从磁盘移除。"
            + "\n当前页面里的正文和布局不会被清空。"
        )
    ){
        return;
    }


    try{

        setTemplateStatus(
            "正在删除模板..."
        );


        const res =
            await fetch(
                "/api/templates/"
                + encodeURIComponent(
                    templateId
                ),
                {
                    method:"DELETE"
                }
            );


        const data =
            await res.json();


        if(!data.success){

            throw new Error(
                data.error
                || "删除模板失败"
            );

        }


        if(
            currentTemplateId
            === templateId
        ){

            currentTemplateId =
                null;

            currentTemplateName =
                "";

        }


        if(
            defaultTemplateId
            === templateId
        ){

            defaultTemplateId =
                null;

        }


        await loadTemplateList(
            null,
            false
        );


        select.value =
            "";


        setTemplateStatus(
            "已删除模板："
            + templateName
            + "；当前编辑内容仍保留"
        );

    }
    catch(e){

        console.error(
            "删除模板失败",
            e
        );

        alert(
            "删除模板失败："
            + e.message
        );

        setTemplateStatus(
            "删除模板失败"
        );

    }

}

function newTemplate(){

    if(
        !confirm(
            "新建模板会清空病区、姓名、床号、住院号和正文。"
            + "\n布局、字体和手写设置会保留。"
            + "\n\n继续吗？"
        )
    ){
        return;
    }


    if(renderedPreview){

        showEditorCanvas();

    }


    if(layoutEditing){

        layoutEditing =
            false;

        document
            .getElementById(
                "previewFrame"
            )
            .classList.remove(
                "editing"
            );

        document
            .getElementById(
                "layoutEditBtn"
            )
            .textContent =
            "编辑布局";

    }


    fieldNames.forEach(
        name => {

            const input =
                document.getElementById(
                    name
                );

            if(input){
                input.value = "";
            }

        }
    );


    getEditor().innerHTML =
        "";


    currentTemplateId =
        null;

    currentTemplateName =
        "";


    document
        .getElementById(
            "templateSelect"
        )
        .value = "";


    invalidateGeneratedTask();

    updateCanvasText();


    setTemplateStatus(
        "新模板：布局和文字设置已保留"
    );

}


/* ===============================
   加载旧的默认 template.json
   （作为程序首次打开时的基础内容）
================================ */

async function loadTemplate(){

    try{

        const res =
            await fetch("/template");

        const data =
            await res.json();

        if(!data.success){
            return;
        }

        if(data.text){

            document
                .getElementById(
                    "text_content"
                )
                .textContent =
                data.text;

        }

        fieldNames.forEach(key=>{

            if(
                data[key] !== undefined
                &&
                data[key] !== ""
            ){

                const el =
                    document
                        .getElementById(
                            key
                        );

                if(el){
                    el.value =
                        data[key];
                }

            }

        });

    }
    catch(e){

        console.error(
            "加载模板失败",
            e
        );

    }

}


/* ===============================
   字体
================================ */

async function loadFonts(){

    const select =
        document.getElementById(
            "font"
        );

    try{

        const res =
            await fetch(
                "/api/fonts"
            );

        const data =
            await res.json();

        if(!data.success){

            select.innerHTML =
                `<option value="">
                    字体加载失败
                </option>`;

            return;
        }

        select.innerHTML = "";

        if(
            !data.fonts
            ||
            data.fonts.length === 0
        ){

            select.innerHTML =
                `<option value="">
                    没有可用字体
                </option>`;

            return;
        }

        data.fonts.forEach(
            fontName => {

                const option =
                    document.createElement(
                        "option"
                    );

                option.value =
                    fontName;

                option.textContent =
                    fontName;

                if(
                    fontName
                    === data.default
                ){
                    option.selected =
                        true;
                }

                select.appendChild(
                    option
                );

            }
        );

    }
    catch(e){

        console.error(
            "加载字体失败",
            e
        );

    }

}


/* ===============================
   设置
================================ */

const settingsConfig = [

    [
        "font_size",
        "字体大小",
        8,
        60,
        15
    ],

    [
        "line_height",
        "行间距",
        10,
        100,
        30
    ],

    [
        "letter_spacing",
        "字间距",
        0,
        20,
        0
    ],

    [
        "line_jitter",
        "行抖动",
        0,
        10,
        3
    ],

    [
        "char_jitter",
        "字抖动",
        0,
        10,
        2
    ]

];


function createSettingsConfig(){

    const textBox =
        document.getElementById(
            "text"
        );

    const effectBox =
        document.getElementById(
            "effectsSettings"
        );

    settingsConfig.forEach(
        item => {

            const html = `

                <div class="form-group">

                    <label>
                        ${item[1]}
                    </label>

                    <input
                        type="number"
                        id="${item[0]}"
                        min="${item[2]}"
                        max="${item[3]}"
                        value="${item[4]}"
                    >

                </div>

            `;

            if(
                item[0] === "line_jitter"
                ||
                item[0] === "char_jitter"
            ){

                effectBox.innerHTML +=
                    html;

            }
            else{

                textBox.innerHTML +=
                    html;

            }

        }
    );

}


/* ===============================
   Tab
================================ */

function switchTab(
    id,
    btn
){

    document
        .querySelectorAll(
            ".tab-content"
        )
        .forEach(
            x =>
                x.classList.remove(
                    "active"
                )
        );

    document
        .querySelectorAll(
            ".tab-button"
        )
        .forEach(
            x =>
                x.classList.remove(
                    "active"
                )
        );

    document
        .getElementById(id)
        .classList.add(
            "active"
        );

    btn.classList.add(
        "active"
    );

}


/* ===============================
   字段
================================ */

function getFields(){

    const data = {};

    fieldNames.forEach(
        name => {

            const el =
                document.getElementById(
                    name
                );

            data[name] =
                el
                ? el.value
                : "";

        }
    );

    return data;

}


/* =========================================================
   坐标换算
========================================================= */

function getCanvasScale(){

    const image =
        document.getElementById(
            "canvasImage"
        );

    if(
        !image.naturalWidth
        ||
        !image.clientWidth
    ){
        return {
            x:1,
            y:1
        };
    }

    return {

        x:
            image.naturalWidth
            / image.clientWidth,

        y:
            image.naturalHeight
            / image.clientHeight

    };

}


function getImagePixelLayout(){

    const scale =
        getCanvasScale();

    const result = {};

    document
        .querySelectorAll(
            ".layout-box"
        )
        .forEach(
            box => {

                const name =
                    box.dataset.box;

                result[name] = {

                    x:
                        Math.round(
                            box.offsetLeft
                            * scale.x
                        ),

                    y:
                        Math.round(
                            box.offsetTop
                            * scale.y
                        ),

                    width:
                        Math.round(
                            box.offsetWidth
                            * scale.x
                        ),

                    height:
                        Math.round(
                            box.offsetHeight
                            * scale.y
                        )

                };

            }
        );

    return result;

}


function applyImagePixelLayout(
    layout
){

    if(
        !layout
        ||
        Object.keys(
            layout
        ).length === 0
    ){
        return;
    }

    const scale =
        getCanvasScale();

    Object.entries(
        layout
    )
    .forEach(
        ([name, config]) => {

            const box =
                document.getElementById(
                    "box_" + name
                );

            if(!box){
                return;
            }

            box.style.left =
                (
                    config.x
                    / scale.x
                )
                + "px";

            box.style.top =
                (
                    config.y
                    / scale.y
                )
                + "px";

            box.style.width =
                (
                    config.width
                    / scale.x
                )
                + "px";

            box.style.height =
                (
                    config.height
                    / scale.y
                )
                + "px";

        }
    );

}


/* ===============================
   初始布局
================================ */

const initialBoxLayoutRatio = {

    "病区":{
        x:0.11,
        y:0.202,
        width:0.16,
        height:0.035
    },

    "姓名":{
        x:0.30,
        y:0.202,
        width:0.14,
        height:0.035
    },

    "床号":{
        x:0.47,
        y:0.202,
        width:0.11,
        height:0.035
    },

    "住院号":{
        x:0.72,
        y:0.202,
        width:0.19,
        height:0.035
    },

    "正文":{
        x:0.10,
        y:0.235,
        width:0.81,
        height:0.70
    }

};


function createInitialImageLayout(){

    const image =
        document.getElementById(
            "canvasImage"
        );

    const result = {};

    Object.entries(
        initialBoxLayoutRatio
    )
    .forEach(
        ([name, config]) => {

            result[name] = {

                x:
                    Math.round(
                        image.naturalWidth
                        * config.x
                    ),

                y:
                    Math.round(
                        image.naturalHeight
                        * config.y
                    ),

                width:
                    Math.round(
                        image.naturalWidth
                        * config.width
                    ),

                height:
                    Math.round(
                        image.naturalHeight
                        * config.height
                    )

            };

        }
    );

    return result;

}


/* =========================================================
   编辑器 / 多页预览切换
========================================================= */

function showEditorCanvas(){

    const stage =
        document.getElementById(
            "previewFrame"
        );

    const pages =
        document.getElementById(
            "renderedPages"
        );

    stage.style.display =
        "block";

    pages.classList.remove(
        "active"
    );

    renderedPreview =
        false;

    applyImagePixelLayout(
        savedImageLayout
    );

    updateCanvasText();

}


function showRenderedPages(
    previewUrls
){

    const stage =
        document.getElementById(
            "previewFrame"
        );

    const pages =
        document.getElementById(
            "renderedPages"
        );

    pages.innerHTML = "";

    previewUrls.forEach(
        (url, index) => {

            const wrapper =
                document.createElement(
                    "div"
                );

            wrapper.className =
                "rendered-page";


            const label =
                document.createElement(
                    "div"
                );

            label.className =
                "rendered-page-label";

            label.textContent =
                `第 ${index + 1} 页`;


            const img =
                document.createElement(
                    "img"
                );

            img.src =
                url
                + "?t="
                + Date.now();

            img.alt =
                `第 ${index + 1} 页`;


            wrapper.appendChild(
                label
            );

            wrapper.appendChild(
                img
            );

            pages.appendChild(
                wrapper
            );

        }
    );


    stage.style.display =
        "none";

    pages.classList.add(
        "active"
    );

    renderedPreview =
        true;

}


/* =========================================================
   编辑 / 完成
========================================================= */

function toggleLayoutEdit(){

    const stage =
        document.getElementById(
            "previewFrame"
        );

    const button =
        document.getElementById(
            "layoutEditBtn"
        );


    if(
        !layoutEditing
        &&
        renderedPreview
    ){
        showEditorCanvas();
    }


    layoutEditing =
        !layoutEditing;


    if(layoutEditing){

        invalidateGeneratedTask();

        stage.classList.add(
            "editing"
        );

        button.textContent =
            "完成";

    }
    else{

        stage.classList.remove(
            "editing"
        );

        document
            .querySelectorAll(
                ".layout-box"
            )
            .forEach(
                item =>
                    item.classList.remove(
                        "active"
                    )
            );

        button.textContent =
            "编辑布局";

        savedImageLayout =
            getImagePixelLayout();

        console.log(
            "已保存原图像素布局：",
            savedImageLayout
        );

    }

}


/* =========================================================
   拖动
========================================================= */

function enableBoxDrag(
    box
){

    let dragging = false;

    let startMouseX = 0;
    let startMouseY = 0;

    let startBoxX = 0;
    let startBoxY = 0;


    box.addEventListener(
        "pointerdown",
        function(e){

            if(!layoutEditing){
                return;
            }

            if(
                e.target
                    .classList
                    .contains(
                        "resize-handle"
                    )
            ){
                return;
            }

            dragging = true;

            box.setPointerCapture(
                e.pointerId
            );

            startMouseX =
                e.clientX;

            startMouseY =
                e.clientY;

            startBoxX =
                box.offsetLeft;

            startBoxY =
                box.offsetTop;


            document
                .querySelectorAll(
                    ".layout-box"
                )
                .forEach(
                    item =>
                        item.classList.remove(
                            "active"
                        )
                );

            box.classList.add(
                "active"
            );

        }
    );


    box.addEventListener(
        "pointermove",
        function(e){

            if(!dragging){
                return;
            }

            const stage =
                document.getElementById(
                    "previewFrame"
                );

            const dx =
                e.clientX
                - startMouseX;

            const dy =
                e.clientY
                - startMouseY;

            let newX =
                startBoxX
                + dx;

            let newY =
                startBoxY
                + dy;

            newX =
                Math.max(
                    0,
                    Math.min(
                        newX,
                        stage.clientWidth
                        - box.offsetWidth
                    )
                );

            newY =
                Math.max(
                    0,
                    Math.min(
                        newY,
                        stage.clientHeight
                        - box.offsetHeight
                    )
                );

            box.style.left =
                newX + "px";

            box.style.top =
                newY + "px";

        }
    );


    function finishDrag(){

        if(!dragging){
            return;
        }

        dragging = false;

        savedImageLayout =
            getImagePixelLayout();

    }


    box.addEventListener(
        "pointerup",
        finishDrag
    );

    box.addEventListener(
        "pointercancel",
        finishDrag
    );

}


/* =========================================================
   缩放
========================================================= */

function enableBoxResize(
    box
){

    const handle =
        box.querySelector(
            ".resize-handle"
        );

    if(!handle){
        return;
    }

    let resizing = false;

    let startMouseX = 0;
    let startMouseY = 0;

    let startWidth = 0;
    let startHeight = 0;


    handle.addEventListener(
        "pointerdown",
        function(e){

            if(!layoutEditing){
                return;
            }

            e.stopPropagation();

            resizing = true;

            handle.setPointerCapture(
                e.pointerId
            );

            startMouseX =
                e.clientX;

            startMouseY =
                e.clientY;

            startWidth =
                box.offsetWidth;

            startHeight =
                box.offsetHeight;

        }
    );


    handle.addEventListener(
        "pointermove",
        function(e){

            if(!resizing){
                return;
            }

            const stage =
                document.getElementById(
                    "previewFrame"
                );

            const dx =
                e.clientX
                - startMouseX;

            const dy =
                e.clientY
                - startMouseY;

            let newWidth =
                startWidth
                + dx;

            let newHeight =
                startHeight
                + dy;

            newWidth =
                Math.max(
                    40,
                    Math.min(
                        newWidth,
                        stage.clientWidth
                        - box.offsetLeft
                    )
                );

            newHeight =
                Math.max(
                    30,
                    Math.min(
                        newHeight,
                        stage.clientHeight
                        - box.offsetTop
                    )
                );

            box.style.width =
                newWidth + "px";

            box.style.height =
                newHeight + "px";

        }
    );


    function finishResize(){

        if(!resizing){
            return;
        }

        resizing = false;

        savedImageLayout =
            getImagePixelLayout();

    }


    handle.addEventListener(
        "pointerup",
        finishResize
    );

    handle.addEventListener(
        "pointercancel",
        finishResize
    );

}


function initLayoutBoxes(){

    document
        .querySelectorAll(
            ".layout-box"
        )
        .forEach(
            box => {

                enableBoxDrag(
                    box
                );

                enableBoxResize(
                    box
                );

            }
        );

}


/* =========================================================
   前端即时文字
========================================================= */

function updateCanvasText(){

    fieldNames.forEach(
        name => {

            const input =
                document.getElementById(
                    name
                );

            const text =
                document.querySelector(
                    "#box_"
                    + name
                    + " .box-text"
                );

            if(
                input
                &&
                text
            ){

                text.textContent =
                    input.value
                    || name;

            }

        }
    );


    const textarea =
        document.getElementById(
            "text_content"
        );

    const bodyText =
        document.querySelector(
            "#box_正文 .box-text"
        );

    if(
        textarea
        &&
        bodyText
    ){

        bodyText.textContent =
            getEditorPlainText()
            || "正文区域";

    }

    applyPreviewTextSettings();

}


function applyPreviewTextSettings(){

    const fontSize =
        Number(
            document
                .getElementById(
                    "font_size"
                )
                .value
        );

    const lineHeight =
        Number(
            document
                .getElementById(
                    "line_height"
                )
                .value
        );

    const letterSpacing =
        Number(
            document
                .getElementById(
                    "letter_spacing"
                )
                .value
        );


    document
        .querySelectorAll(
            ".box-text"
        )
        .forEach(
            element => {

                element.style.fontSize =
                    Math.max(
                        8,
                        fontSize
                    )
                    + "px";

                element.style.letterSpacing =
                    letterSpacing
                    + "px";

            }
        );


    const bodyText =
        document.querySelector(
            "#box_正文 .box-text"
        );

    if(bodyText){

        bodyText.style.lineHeight =
            Math.max(
                10,
                lineHeight
            )
            + "px";

    }

}


/* =========================================================
   原图像素设置
========================================================= */

function getRenderSettings(){

    const scale =
        getCanvasScale();

    return {

        font:
            document
                .getElementById(
                    "font"
                )
                .value,

        font_size:
            Math.max(
                1,
                Math.round(
                    Number(
                        document
                            .getElementById(
                                "font_size"
                            )
                            .value
                    )
                    * scale.y
                )
            ),

        line_height:
            Math.max(
                1,
                Math.round(
                    Number(
                        document
                            .getElementById(
                                "line_height"
                            )
                            .value
                    )
                    * scale.y
                )
            ),

        letter_spacing:
            Number(
                document
                    .getElementById(
                        "letter_spacing"
                    )
                    .value
            )
            * scale.x,

        line_jitter:
            Number(
                document
                    .getElementById(
                        "line_jitter"
                    )
                    .value
            )
            * scale.y,

        char_jitter:
            Number(
                document
                    .getElementById(
                        "char_jitter"
                    )
                    .value
            )
            * scale.x

    };

}


/* =========================================================
   Pillow 多页预览
========================================================= */

async function generatePreview(){

    if(layoutEditing){

        alert(
            "请先点击“完成”保存当前布局"
        );

        return;
    }


    const text =
        getEditorPlainText();

    if(!text){

        alert(
            "请输入文本内容"
        );

        return;
    }


    /*
        如果当前正在显示真实预览，
        先回到编辑画布读取正确的缩放比例。
    */
    if(renderedPreview){
        showEditorCanvas();
    }


    savedImageLayout =
        getImagePixelLayout();


    const previewButton =
        document.getElementById(
            "previewBtn"
        );

    previewButton.disabled =
        true;

    previewButton.textContent =
        "生成中...";


    try{

        const res =
            await fetch(
                "/preview_image",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            text:text,

                            fields:
                                getFields(),

                            boxes:
                                savedImageLayout,

                            settings:
                                getRenderSettings(),

                            background_id:
                                currentBackgroundId

                        })

                }
            );


        const data =
            await res.json();


        if(!data.success){

            alert(
                data.error
                || "图片生成失败"
            );

            return;
        }


        currentTaskId =
            data.task_id;

        currentPageCount =
            data.page_count;


        document
            .getElementById(
                "downloadAllImages"
            )
            .disabled = false;


        showRenderedPages(
            data.preview_urls
        );


        console.log(
            `已生成 ${data.page_count} 页`,
            data
        );

    }
    catch(e){

        console.error(e);

        alert(
            "请求图片预览失败："
            + e
        );

    }
    finally{

        previewButton.disabled =
            false;

        previewButton.textContent =
            "预览生成效果";

    }

}


/* ===============================
   下载 JPG ZIP
================================ */

function downloadAllImages(){

    if(!currentTaskId){

        alert(
            "请先生成图片预览"
        );

        return;
    }

    window.location.href =
        "/download_images/"
        + encodeURIComponent(
            currentTaskId
        );

}


/* ===============================
   输入绑定
================================ */

function bindCanvasInputs(){

    [
        "病区",
        "姓名",
        "床号",
        "住院号",
        "text_content"
    ]
    .forEach(
        id => {

            const element =
                document.getElementById(
                    id
                );

            if(!element){
                return;
            }

            element.addEventListener(
                "input",
                function(){

                    invalidateGeneratedTask();

                    updateCanvasText();

                }
            );

        }
    );


    [
        "font_size",
        "line_height",
        "letter_spacing"
    ]
    .forEach(
        id => {

            const element =
                document.getElementById(
                    id
                );

            if(!element){
                return;
            }

            element.addEventListener(
                "input",
                function(){

                    invalidateGeneratedTask();

                    applyPreviewTextSettings();

                }
            );

        }
    );

}


/* ===============================
   浏览器尺寸变化
================================ */

window.addEventListener(
    "resize",
    function(){

        if(
            !renderedPreview
            &&
            Object.keys(
                savedImageLayout
            ).length > 0
        ){

            applyImagePixelLayout(
                savedImageLayout
            );

        }

    }
);


/* ===============================
   初始化
================================ */

createSettingsConfig();


window.addEventListener(
    "DOMContentLoaded",
    async function(){

        await loadTemplate();

        await loadFonts();

        const canvasImage =
            document.getElementById(
                "canvasImage"
            );

        let initialized =
            false;


        async function initializeEditor(){

            if(initialized){
                return;
            }

            initialized =
                true;

            savedImageLayout =
                createInitialImageLayout();

            applyImagePixelLayout(
                savedImageLayout
            );

            initLayoutBoxes();

            initTemplateEditor();

            bindCanvasInputs();

            updateCanvasText();

            await loadTemplateList(
                null,
                true
            );
                // 模板加载完以后，直接生成真正的 Pillow 手写图片
            if(
                getEditorPlainText()
                    .trim()
            ){
                await generatePreview();
            }

            console.log(
                "base.jpg 原始尺寸：",
                {
                    width:
                        canvasImage
                            .naturalWidth,

                    height:
                        canvasImage
                            .naturalHeight
                }
            );

            console.log(
                "初始原图像素布局：",
                savedImageLayout
            );

        }


        if(
            canvasImage.complete
            &&
            canvasImage.naturalWidth > 0
        ){

            initializeEditor();

        }
        else{

            canvasImage.addEventListener(
                "load",
                initializeEditor,
                {
                    once:true
                }
            );

        }

    }
);
